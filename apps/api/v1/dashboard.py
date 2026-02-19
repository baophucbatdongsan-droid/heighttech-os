# apps/api/v1/dashboard.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from django.db.models import Sum
from django.utils.dateparse import parse_date

from rest_framework.permissions import IsAuthenticated

from apps.api.v1.base import BaseApi, api_ok
from apps.api.v1.permissions import AbilityPermission
from apps.api.v1.guards import filter_perf_queryset_for_user
from apps.core.policy import VIEW_API_DASHBOARD
from apps.performance.models import MonthlyPerformance


def _has_field(model, field_name: str) -> bool:
    try:
        return any(f.name == field_name for f in model._meta.get_fields())
    except Exception:
        return False


def _sum_safe(qs, field: str) -> Decimal:
    if not qs or not hasattr(qs, "model"):
        return Decimal("0")
    if not _has_field(qs.model, field):
        return Decimal("0")
    return qs.aggregate(total=Sum(field))["total"] or Decimal("0")


class DashboardApi(BaseApi):
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def get(self, request):
        month = request.GET.get("month")          # YYYY-MM-01
        company_id = request.GET.get("company")   # optional

        qs = MonthlyPerformance.objects.all()
        qs = filter_perf_queryset_for_user(request.user, qs)

        # filter month
        if month and _has_field(MonthlyPerformance, "month"):
            d = parse_date(month)
            if d:
                qs = qs.filter(month=d)

        # filter company (chỉ là filter thêm, vẫn nằm trong scope)
        if company_id:
            try:
                cid = int(company_id)
                if _has_field(MonthlyPerformance, "company"):
                    qs = qs.filter(company_id=cid)
                elif _has_field(MonthlyPerformance, "shop"):
                    qs = qs.filter(shop__brand__company_id=cid)
            except Exception:
                pass

        total_revenue = _sum_safe(qs, "revenue")
        total_profit = _sum_safe(qs, "profit")
        total_net = _sum_safe(qs, "company_net_profit")

        base = total_net if total_net != 0 else total_profit
        margin = (base / total_revenue * Decimal("100")) if total_revenue > 0 else Decimal("0")

        months: List[str] = []
        revenues: List[float] = []
        profits: List[float] = []

        if (
            _has_field(MonthlyPerformance, "month")
            and _has_field(MonthlyPerformance, "revenue")
            and _has_field(MonthlyPerformance, "profit")
        ):
            monthly = (
                qs.values("month")
                .annotate(revenue=Sum("revenue"), profit=Sum("profit"))
                .order_by("month")
            )
            for row in monthly:
                m = row.get("month")
                months.append(m.strftime("%m/%Y") if m else "")
                revenues.append(float(row.get("revenue") or 0))
                profits.append(float(row.get("profit") or 0))

        data: Dict[str, Any] = {
            "filters": {"month": month or "", "company": company_id or ""},
            "kpi": {
                "total_revenue": float(total_revenue),
                "total_profit": float(total_profit),
                "total_net": float(total_net),
                "margin": float(margin.quantize(Decimal("0.01"))),
            },
            "chart": {"months": months, "revenues": revenues, "profits": profits},
        }
        return api_ok(data)