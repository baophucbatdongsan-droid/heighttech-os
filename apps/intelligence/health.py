# apps/intelligence/health.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple

from django.db.models import QuerySet
from django.utils import timezone


def d(x) -> Decimal:
    return Decimal(str(x or "0"))


def q2(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class ShopHealth:
    shop_id: int
    shop_name: str
    brand_name: str
    company_name: str

    # last 3 months snapshots
    last_month: Optional[str]              # "MM/YYYY"
    revenue_3m: Decimal
    profit_3m: Decimal
    margin_3m: Decimal                     # %
    growth_last_mom: Decimal               # %

    # flags
    flag_negative_2m: bool
    flag_low_margin: bool
    flag_drop_revenue: bool

    # final
    score: int                             # 0-100
    risk: str                              # "LOW/MED/HIGH"
    note: str


class ShopHealthService:
    """
    Shop Health Engine
    - Đọc MonthlyPerformance (shop-level)
    - Tính 3M revenue/profit/margin
    - Tính MoM growth (revenue tháng gần nhất vs tháng trước)
    - Sinh flags + score 0-100
    """

    LOW_MARGIN_THRESHOLD = Decimal("15")   # <15% coi là rủi ro
    DROP_REV_THRESHOLD = Decimal("20")     # giảm >20% MoM => cảnh báo

    @staticmethod
    def _format_month(dt) -> str:
        return dt.strftime("%m/%Y")

    @staticmethod
    def _get_base_queryset(month: Optional[str] = None) -> QuerySet:
        """
        month: "YYYY-MM-01" optional
        - Nếu có month: chỉ lấy <= month
        - Nếu không: lấy tất cả
        """
        from apps.performance.models import MonthlyPerformance

        qs = MonthlyPerformance.objects.select_related(
            "shop",
            "shop__brand",
            "shop__brand__company",
        )

        if month:
            # month string "YYYY-MM-01"
            # SQLite ok with date string; Django will cast
            qs = qs.filter(month__lte=month)

        return qs

    @staticmethod
    def _get_last_n_per_shop(qs: QuerySet, n: int = 3) -> Dict[int, List]:
        """
        Trả về dict[shop_id] = list(perf) order desc by month
        """
        rows = qs.order_by("shop_id", "-month")

        buckets: Dict[int, List] = {}
        for p in rows:
            sid = p.shop_id
            if sid not in buckets:
                buckets[sid] = []
            if len(buckets[sid]) < n:
                buckets[sid].append(p)
        return buckets

    @staticmethod
    def _score(
        revenue_3m: Decimal,
        profit_3m: Decimal,
        margin_3m: Decimal,
        growth_mom: Decimal,
        flag_negative_2m: bool,
        flag_low_margin: bool,
        flag_drop_revenue: bool,
    ) -> Tuple[int, str, str]:
        """
        Score logic: thực dụng, không màu mè.
        Start 100, trừ dần theo risk.
        """
        score = 100
        notes: List[str] = []

        # core health
        if revenue_3m <= 0:
            score -= 40
            notes.append("No revenue 3M")

        if profit_3m < 0:
            score -= 30
            notes.append("Profit 3M negative")

        # margin
        if flag_low_margin:
            score -= 20
            notes.append(f"Low margin < {ShopHealthService.LOW_MARGIN_THRESHOLD}%")

        # growth
        if flag_drop_revenue:
            score -= 20
            notes.append(f"Revenue drop > {ShopHealthService.DROP_REV_THRESHOLD}% MoM")

        if flag_negative_2m:
            score -= 25
            notes.append("Negative profit 2 months consecutive")

        # bonus for strong growth with good margin
        if growth_mom >= Decimal("25") and margin_3m >= Decimal("20"):
            score += 5
            notes.append("Strong growth + healthy margin")

        # clamp
        if score < 0:
            score = 0
        if score > 100:
            score = 100

        # risk
        if score >= 75:
            risk = "LOW"
        elif score >= 50:
            risk = "MED"
        else:
            risk = "HIGH"

        note = " | ".join(notes) if notes else "Healthy"
        return score, risk, note

    @staticmethod
    def build_shop_health(month: Optional[str] = None) -> List[ShopHealth]:
        """
        Trả list ShopHealth, sort theo risk (HIGH trước), score tăng dần.
        """
        qs = ShopHealthService._get_base_queryset(month=month)
        buckets = ShopHealthService._get_last_n_per_shop(qs, n=3)

        result: List[ShopHealth] = []

        for shop_id, perfs in buckets.items():
            # perfs: [latest, prev, prev2] (desc)
            latest = perfs[0]
            prev = perfs[1] if len(perfs) >= 2 else None
            prev2 = perfs[2] if len(perfs) >= 3 else None

            # sums 3m
            rev_3m = d(sum([d(p.revenue) for p in perfs]))
            prof_3m = d(sum([d(p.profit) for p in perfs]))

            # margin 3m
            margin_3m = Decimal("0")
            if rev_3m > 0:
                margin_3m = (prof_3m / rev_3m) * Decimal("100")

            # MoM growth based on revenue latest vs prev
            growth_mom = Decimal("0")
            if prev and d(prev.revenue) > 0:
                growth_mom = ((d(latest.revenue) - d(prev.revenue)) / d(prev.revenue)) * Decimal("100")

            # flags
            flag_negative_2m = False
            if prev:
                if d(latest.profit) < 0 and d(prev.profit) < 0:
                    flag_negative_2m = True

            flag_low_margin = margin_3m < ShopHealthService.LOW_MARGIN_THRESHOLD if rev_3m > 0 else True

            flag_drop_revenue = False
            if prev and d(prev.revenue) > 0:
                drop = ((d(prev.revenue) - d(latest.revenue)) / d(prev.revenue)) * Decimal("100")
                if drop >= ShopHealthService.DROP_REV_THRESHOLD:
                    flag_drop_revenue = True

            score, risk, note = ShopHealthService._score(
                revenue_3m=rev_3m,
                profit_3m=prof_3m,
                margin_3m=margin_3m,
                growth_mom=growth_mom,
                flag_negative_2m=flag_negative_2m,
                flag_low_margin=flag_low_margin,
                flag_drop_revenue=flag_drop_revenue,
            )

            result.append(
                ShopHealth(
                    shop_id=shop_id,
                    shop_name=latest.shop.name,
                    brand_name=latest.shop.brand.name,
                    company_name=latest.shop.brand.company.name,

                    last_month=ShopHealthService._format_month(latest.month),

                    revenue_3m=q2(rev_3m),
                    profit_3m=q2(prof_3m),
                    margin_3m=q2(margin_3m),
                    growth_last_mom=q2(growth_mom),

                    flag_negative_2m=flag_negative_2m,
                    flag_low_margin=flag_low_margin,
                    flag_drop_revenue=flag_drop_revenue,

                    score=int(score),
                    risk=risk,
                    note=note,
                )
            )

        # sort: HIGH first, then lowest score first
        risk_order = {"HIGH": 0, "MED": 1, "LOW": 2}
        result.sort(key=lambda x: (risk_order.get(x.risk, 9), x.score))
        return result