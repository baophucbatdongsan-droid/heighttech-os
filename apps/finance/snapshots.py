from decimal import Decimal
from django.db.models import Sum
from django.utils.dateparse import parse_date

from apps.performance.models import MonthlyPerformance
from apps.finance.models import CompanyMonthlySnapshot, ShopMonthlySnapshot


class SnapshotService:
    @staticmethod
    def rebuild_month(month_str: str):
        """
        Build snapshot cho 1 tháng: YYYY-MM-01
        """
        month = parse_date(month_str)
        if not month:
            raise ValueError("Month format phải là YYYY-MM-DD")

        qs = MonthlyPerformance.objects.filter(month=month).select_related(
            "shop", "shop__brand", "shop__brand__company"
        )

        # -----------------------
        # SHOP SNAPSHOT
        # -----------------------
        shop_ids = qs.values_list("shop_id", flat=True).distinct()

        for shop_id in shop_ids:
            shop_qs = qs.filter(shop_id=shop_id)

            revenue = shop_qs.aggregate(t=Sum("revenue"))["t"] or Decimal("0")
            profit = shop_qs.aggregate(t=Sum("profit"))["t"] or Decimal("0")
            net = shop_qs.aggregate(t=Sum("company_net_profit"))["t"] or Decimal("0")

            margin = Decimal("0")
            if revenue > 0:
                margin = (net / revenue) * Decimal("100")

            score = 100
            risk = "LOW"

            if margin < 5:
                score -= 35
            if net < 0:
                score -= 30

            if score < 45:
                risk = "HIGH"
            elif score < 70:
                risk = "MED"

            ShopMonthlySnapshot.objects.update_or_create(
                shop_id=shop_id,
                month=month,
                defaults={
                    "revenue": revenue,
                    "profit": profit,
                    "net": net,
                    "margin": margin,
                    "score": max(0, min(100, score)),
                    "risk": risk,
                },
            )

        # -----------------------
        # COMPANY SNAPSHOT
        # -----------------------
        company_ids = qs.values_list("shop__brand__company_id", flat=True).distinct()

        for company_id in company_ids:
            company_qs = qs.filter(shop__brand__company_id=company_id)

            revenue = company_qs.aggregate(t=Sum("revenue"))["t"] or Decimal("0")
            profit = company_qs.aggregate(t=Sum("profit"))["t"] or Decimal("0")
            net = company_qs.aggregate(t=Sum("company_net_profit"))["t"] or Decimal("0")

            margin = Decimal("0")
            if revenue > 0:
                margin = (net / revenue) * Decimal("100")

            CompanyMonthlySnapshot.objects.update_or_create(
                company_id=company_id,
                month=month,
                defaults={
                    "total_revenue": revenue,
                    "total_profit": profit,
                    "total_net": net,
                    "margin": margin,
                },
            )