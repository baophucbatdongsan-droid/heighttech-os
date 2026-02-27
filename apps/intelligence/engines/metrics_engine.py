from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Dict, Any, Optional

from django.db.models import Sum
from django.utils.dateparse import parse_date

from apps.performance.models import MonthlyPerformance


def _d(value) -> Decimal:
    return Decimal(str(value or "0"))


class MetricsEngine:
    """
    System-level metrics engine (Founder layer).

    Chỉ chịu trách nhiệm:
    - Revenue
    - Profit
    - Net
    - Margin
    - Burn rate
    - Runway
    - Top companies
    - Loss companies
    """

    @staticmethod
    def build(month: Optional[str] = None) -> Dict[str, Any]:

        qs = (
            MonthlyPerformance.objects
            .select_related("shop", "shop__brand", "shop__brand__company")
        )

        selected_month: Optional[date] = None

        if month:
            parsed = parse_date(month)
            if parsed:
                selected_month = parsed
                qs = qs.filter(month=parsed)

        total_revenue = qs.aggregate(t=Sum("revenue"))["t"] or Decimal("0")
        total_profit = qs.aggregate(t=Sum("profit"))["t"] or Decimal("0")
        total_net = qs.aggregate(t=Sum("company_net_profit"))["t"] or Decimal("0")

        margin = Decimal("0")
        if _d(total_revenue) > 0:
            margin = (_d(total_net) / _d(total_revenue)) * Decimal("100")

        # Founder có thể set sau (internal config)
        burn_rate = Decimal("0")
        runway_months = Decimal("0")

        if burn_rate != 0:
            runway_months = abs(_d(total_net) / burn_rate)

        # Top companies theo revenue
        top_companies = (
            qs.values("shop__brand__company__name")
            .annotate(total_revenue=Sum("revenue"))
            .order_by("-total_revenue")[:10]
        )

        # Company đang lỗ
        loss_companies = (
            qs.values("shop__brand__company__name")
            .annotate(total_net=Sum("company_net_profit"))
            .filter(total_net__lt=0)
            .order_by("total_net")[:20]
        )

        return {
            "selected_month": selected_month.isoformat() if selected_month else "",
            "total_revenue": total_revenue,
            "total_profit": total_profit,
            "total_net": total_net,
            "margin": float(margin.quantize(Decimal("0.01"))),
            "burn_rate": burn_rate,
            "runway_months": float(runway_months) if runway_months else 0,
            "top_companies": top_companies,
            "loss_companies": loss_companies,
        }