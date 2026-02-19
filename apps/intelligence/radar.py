# apps/intelligence/radar.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from django.db.models import Sum, Avg, F, Q
from django.utils import timezone

from apps.performance.models import MonthlyPerformance


def _as_date_first_day(s: Optional[str]) -> Optional[date]:
    """
    Expect "YYYY-MM-01". Return date or None.
    """
    if not s:
        return None
    try:
        y, m, d = s.split("-")
        return date(int(y), int(m), int(d))
    except Exception:
        return None


def _month_add(d: date, delta_months: int) -> date:
    """
    Add/sub months but keep day=1.
    """
    y = d.year
    m = d.month + delta_months
    while m <= 0:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    return date(y, m, 1)


def _get_latest_month() -> Optional[date]:
    latest = MonthlyPerformance.objects.order_by("-month").values_list("month", flat=True).first()
    return latest


@dataclass
class ShopRadarRow:
    shop_id: int
    shop_name: str
    brand_name: str
    company_name: str

    revenue: Decimal
    gmv_fee_after_tax: Decimal
    team_bonus: Decimal
    sale_commission: Decimal
    company_net_profit: Decimal
    profit_margin_pct: Decimal
    growth_pct: Decimal

    risk_score: int
    risk_reasons: List[str]


class FounderRadarService:
    """
    Founder Radar:
    - Top profit shops (3M)
    - Top risk shops (3M)
    - Revenue up but net down (warning)
    - Loss shops (3M)
    """

    @staticmethod
    def build_radar_context(month: Optional[str] = None, limit: int = 5) -> Dict[str, Any]:
        """
        month: "YYYY-MM-01" (optional)
        If not provided -> auto latest month in DB.
        Uses 3-month window ending at `month`.
        """
        picked = _as_date_first_day(month) or _get_latest_month()
        if not picked:
            # no data yet
            return {
                "radar_month": None,
                "radar_window": [],
                "radar_top_profit_shops": [],
                "radar_top_risk_shops": [],
                "radar_revenue_up_net_down": [],
                "radar_loss_shops": [],
            }

        m2 = _month_add(picked, -2)
        window = [m2, _month_add(picked, -1), picked]

        qs = (
            MonthlyPerformance.objects
            .filter(month__in=window)
            .select_related("shop", "shop__brand", "shop__brand__company")
        )

        # Aggregate per shop across 3 months
        rows = (
            qs.values(
                "shop_id",
                "shop__name",
                "shop__brand__name",
                "shop__brand__company__name",
            )
            .annotate(
                revenue=Sum("revenue"),
                gmv_fee_after_tax=Sum("gmv_fee_after_tax"),
                team_bonus=Sum("bonus_amount"),
                sale_commission=Sum("sale_commission"),
                company_net_profit=Sum("company_net_profit"),
                growth_avg=Avg("growth_percent"),
            )
        )

        # For “revenue up but net down”, we need last month vs prev month per shop
        last_month_qs = qs.filter(month=picked)
        prev_month_qs = qs.filter(month=_month_add(picked, -1))

        last_map = {
            r["shop_id"]: r
            for r in last_month_qs.values("shop_id").annotate(
                rev=Sum("revenue"),
                net=Sum("company_net_profit"),
                margin=Avg(
                    # margin proxy: net / revenue * 100 (avoid div0 later)
                    # not exact per-row but good enough for radar
                    # We'll compute safer in python
                    net_avg=Avg("company_net_profit"),
                ),
            )
        }
        prev_map = {
            r["shop_id"]: r
            for r in prev_month_qs.values("shop_id").annotate(
                rev=Sum("revenue"),
                net=Sum("company_net_profit"),
            )
        }

        radar_rows: List[ShopRadarRow] = []
        for r in rows:
            revenue = Decimal(r["revenue"] or 0)
            net = Decimal(r["company_net_profit"] or 0)
            growth = Decimal(r["growth_avg"] or 0)

            # Margin %
            if revenue > 0:
                margin_pct = (net / revenue) * Decimal("100")
            else:
                margin_pct = Decimal("0")

            risk_score, reasons = FounderRadarService._risk_scoring(
                revenue=revenue,
                net=net,
                margin_pct=margin_pct,
                growth_pct=growth,
                shop_id=r["shop_id"],
                last_map=last_map,
                prev_map=prev_map,
            )

            radar_rows.append(
                ShopRadarRow(
                    shop_id=r["shop_id"],
                    shop_name=r["shop__name"] or "-",
                    brand_name=r["shop__brand__name"] or "-",
                    company_name=r["shop__brand__company__name"] or "-",
                    revenue=revenue,
                    gmv_fee_after_tax=Decimal(r["gmv_fee_after_tax"] or 0),
                    team_bonus=Decimal(r["team_bonus"] or 0),
                    sale_commission=Decimal(r["sale_commission"] or 0),
                    company_net_profit=net,
                    profit_margin_pct=margin_pct,
                    growth_pct=growth,
                    risk_score=risk_score,
                    risk_reasons=reasons,
                )
            )

        # Top profit shops
        top_profit = sorted(radar_rows, key=lambda x: x.company_net_profit, reverse=True)[:limit]

        # Top risk shops
        top_risk = sorted(radar_rows, key=lambda x: (x.risk_score, -x.revenue), reverse=True)[:limit]

        # Loss shops
        loss_shops = [x for x in radar_rows if x.company_net_profit < 0]
        loss_shops = sorted(loss_shops, key=lambda x: x.company_net_profit)[:limit]

        # Revenue up but net down
        revenue_up_net_down = FounderRadarService._revenue_up_net_down(
            radar_rows=radar_rows,
            last_map=last_map,
            prev_map=prev_map,
            limit=limit,
        )

        return {
            "radar_month": picked,
            "radar_window": window,  # [m-2, m-1, m]
            "radar_top_profit_shops": [FounderRadarService._row_to_dict(x) for x in top_profit],
            "radar_top_risk_shops": [FounderRadarService._row_to_dict(x) for x in top_risk],
            "radar_revenue_up_net_down": revenue_up_net_down,
            "radar_loss_shops": [FounderRadarService._row_to_dict(x) for x in loss_shops],
        }

    @staticmethod
    def _risk_scoring(
        revenue: Decimal,
        net: Decimal,
        margin_pct: Decimal,
        growth_pct: Decimal,
        shop_id: int,
        last_map: Dict[int, Dict[str, Any]],
        prev_map: Dict[int, Dict[str, Any]],
    ) -> Tuple[int, List[str]]:
        """
        Risk score 0..100 (heuristic).
        """
        score = 0
        reasons: List[str] = []

        # 1) Net negative (heavy)
        if net < 0:
            score += 45
            reasons.append("Net âm (3M)")

        # 2) Margin too low
        if revenue > 0 and margin_pct < Decimal("3"):
            score += 20
            reasons.append("Margin < 3%")

        # 3) Growth negative
        if growth_pct < 0:
            score += 10
            reasons.append("Tăng trưởng âm")

        # 4) Revenue drop MoM (last vs prev)
        last = last_map.get(shop_id)
        prev = prev_map.get(shop_id)
        if last and prev:
            last_rev = Decimal(last.get("rev") or 0)
            prev_rev = Decimal(prev.get("rev") or 0)
            if prev_rev > 0:
                drop = (prev_rev - last_rev) / prev_rev
                if drop >= Decimal("0.20"):
                    score += 15
                    reasons.append("Doanh thu giảm >= 20% MoM")

        # 5) Revenue exists but net ~0 (leak)
        if revenue > 0 and net <= Decimal("0"):
            score += 10
            reasons.append("Có doanh thu nhưng net không dương")

        if score > 100:
            score = 100
        return score, reasons

    @staticmethod
    def _revenue_up_net_down(
        radar_rows: List[ShopRadarRow],
        last_map: Dict[int, Dict[str, Any]],
        prev_map: Dict[int, Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []

        for r in radar_rows:
            last = last_map.get(r.shop_id)
            prev = prev_map.get(r.shop_id)
            if not last or not prev:
                continue

            last_rev = Decimal(last.get("rev") or 0)
            prev_rev = Decimal(prev.get("rev") or 0)
            last_net = Decimal(last.get("net") or 0)
            prev_net = Decimal(prev.get("net") or 0)

            # revenue up, net down
            if last_rev > prev_rev and last_net < prev_net:
                out.append({
                    "shop_id": r.shop_id,
                    "shop_name": r.shop_name,
                    "brand_name": r.brand_name,
                    "company_name": r.company_name,
                    "prev_revenue": float(prev_rev),
                    "last_revenue": float(last_rev),
                    "prev_net": float(prev_net),
                    "last_net": float(last_net),
                })

        # sort by how bad net dropped
        out.sort(key=lambda x: (x["prev_net"] - x["last_net"]), reverse=True)
        return out[:limit]

    @staticmethod
    def _row_to_dict(r: ShopRadarRow) -> Dict[str, Any]:
        return {
            "shop_id": r.shop_id,
            "shop_name": r.shop_name,
            "brand_name": r.brand_name,
            "company_name": r.company_name,

            "revenue": float(r.revenue),
            "gmv_fee_after_tax": float(r.gmv_fee_after_tax),
            "team_bonus": float(r.team_bonus),
            "sale_commission": float(r.sale_commission),
            "company_net_profit": float(r.company_net_profit),

            "profit_margin_pct": float(r.profit_margin_pct),
            "growth_pct": float(r.growth_pct),

            "risk_score": r.risk_score,
            "risk_reasons": r.risk_reasons,
        }