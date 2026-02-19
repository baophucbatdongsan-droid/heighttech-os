# apps/intelligence/scoring.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional

from django.db.models import QuerySet


def _to_float(x) -> float:
    if x is None:
        return 0.0
    try:
        if isinstance(x, Decimal):
            return float(x)
        return float(x)
    except Exception:
        return 0.0


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _pct(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return (a - b) / b * 100.0


def _std(values: List[float]) -> float:
    n = len(values)
    if n <= 1:
        return 0.0
    mean = sum(values) / n
    var = sum((x - mean) ** 2 for x in values) / (n - 1)
    return var ** 0.5


def _lin_slope(values: List[float]) -> float:
    """
    slope tuyến tính đơn giản theo index (0..n-1).
    """
    n = len(values)
    if n <= 1:
        return 0.0
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(values) / n
    num = sum((xs[i] - x_mean) * (values[i] - y_mean) for i in range(n))
    den = sum((xs[i] - x_mean) ** 2 for i in range(n))
    return (num / den) if den else 0.0


def _trend_forecast(values: List[float], steps: int = 3) -> List[float]:
    """
    Forecast nhẹ: avg delta 2-3 kỳ gần nhất.
    """
    if not values:
        return [0.0] * steps
    if len(values) == 1:
        return [round(values[-1], 2)] * steps

    deltas: List[float] = []
    for i in range(max(1, len(values) - 3), len(values)):
        deltas.append(values[i] - values[i - 1])

    avg_delta = sum(deltas) / len(deltas) if deltas else 0.0
    cur = float(values[-1])
    out: List[float] = []
    for _ in range(steps):
        cur = cur + avg_delta
        out.append(round(cur, 2))
    return out


def _has_field(model, name: str) -> bool:
    try:
        return any(f.name == name for f in model._meta.get_fields())
    except Exception:
        return False


def _get_profit_field(model) -> Optional[str]:
    if _has_field(model, "company_net_profit"):
        return "company_net_profit"
    if _has_field(model, "profit"):
        return "profit"
    return None


@dataclass
class ShopHealthRow:
    shop_id: int
    shop_name: str
    platform: str = ""
    company_name: str = ""

    months: int = 0
    last_month: str = ""

    revenue_last: float = 0.0
    cost_last: float = 0.0
    profit_last: float = 0.0
    margin_last: float = 0.0
    growth_mom: float = 0.0

    stability_score: float = 0.0
    margin_score: float = 0.0
    growth_score: float = 0.0
    loss_risk_score: float = 0.0

    health_score: float = 0.0
    health_badge: str = "UNKNOWN"   # EXCELLENT/GOOD/WARN/CRITICAL
    risk_level: str = "LOW"         # LOW/MEDIUM/HIGH
    notes: str = ""

    # ---- v2 ----
    forecast_next: float = 0.0           # avg forecast next 3
    trend_slope: float = 0.0             # slope doanh thu
    volatility: float = 0.0              # độ biến động doanh thu
    anomaly_flags: List[str] = None      # cảnh báo
    rank_percentile: float = 0.0         # do services set

    # ---- v3 ----
    roi_percent: float = 0.0             # net_profit / cost * 100
    early_warning: bool = False          # cảnh báo sớm


def badge_from_score(score: float) -> str:
    if score >= 85:
        return "EXCELLENT"
    if score >= 70:
        return "GOOD"
    if score >= 50:
        return "WARN"
    return "CRITICAL"


def risk_from_flags(loss_streak: int, growth_mom: float, margin_last: float) -> str:
    if loss_streak >= 2:
        return "HIGH"
    if growth_mom < -10 and margin_last < 3:
        return "HIGH"
    if growth_mom < 0 or margin_last < 5:
        return "MEDIUM"
    return "LOW"


def compute_shop_health_rows(
    *,
    shops_qs: QuerySet,
    perf_qs: QuerySet,
    months_window: int = 6,
) -> List[ShopHealthRow]:
    MP = perf_qs.model
    profit_field = _get_profit_field(MP)
    has_shop_fk = _has_field(MP, "shop")
    has_cost = _has_field(MP, "cost")

    rows: List[ShopHealthRow] = []
    perf_by_shop: dict[int, list] = {}

    if has_shop_fk:
        for p in perf_qs.select_related("shop").order_by("shop_id", "month"):
            sid = getattr(p, "shop_id", None)
            if sid is None:
                continue
            perf_by_shop.setdefault(sid, []).append(p)

    for s in shops_qs:
        sid = getattr(s, "id", 0)
        perf_list = perf_by_shop.get(sid, [])
        if perf_list:
            perf_list = perf_list[-months_window:]

        revs: List[float] = []
        costs: List[float] = []
        profits: List[float] = []
        months: List[str] = []

        for p in perf_list:
            m = getattr(p, "month", None)
            months.append(m.strftime("%m/%Y") if m else "")
            revs.append(_to_float(getattr(p, "revenue", 0)))
            costs.append(_to_float(getattr(p, "cost", 0)) if has_cost else 0.0)
            if profit_field:
                profits.append(_to_float(getattr(p, profit_field, 0)))
            else:
                profits.append(0.0)

        n = len(revs)
        rev_last = revs[-1] if n else 0.0
        cost_last = costs[-1] if n else 0.0
        prof_last = profits[-1] if n else 0.0
        margin_last = (prof_last / rev_last * 100.0) if rev_last > 0 else 0.0

        growth_mom = 0.0
        prev_growth_mom = 0.0
        if n >= 2 and revs[-2] > 0:
            growth_mom = round(_pct(revs[-1], revs[-2]), 2)
        if n >= 3 and revs[-3] > 0:
            prev_growth_mom = round(_pct(revs[-2], revs[-3]), 2)

        # ===== SCORING =====
        stability = 0.0
        if n >= 2:
            mean_rev = sum(revs) / n
            if mean_rev > 0:
                cv = _std(revs) / mean_rev
                stability = _clamp(100.0 - cv * 100.0)
            else:
                stability = 0.0
        else:
            stability = 50.0 if n == 1 and rev_last > 0 else 0.0

        if margin_last <= 0:
            margin_score = 0.0
        elif margin_last >= 15:
            margin_score = 100.0
        else:
            margin_score = _clamp(margin_last / 15.0 * 100.0)

        if growth_mom <= -20:
            growth_score = 0.0
        elif growth_mom >= 20:
            growth_score = 100.0
        else:
            growth_score = _clamp((growth_mom + 20) / 40.0 * 100.0)

        loss_streak = 0
        for x in reversed(profits):
            if x < 0:
                loss_streak += 1
            else:
                break

        if loss_streak == 0:
            loss_risk_score = 100.0
        elif loss_streak == 1:
            loss_risk_score = 60.0
        elif loss_streak == 2:
            loss_risk_score = 20.0
        else:
            loss_risk_score = 0.0

        health = (
            0.30 * stability +
            0.25 * margin_score +
            0.25 * growth_score +
            0.20 * loss_risk_score
        )
        health = round(_clamp(health), 2)

        badge = badge_from_score(health)
        risk = risk_from_flags(loss_streak, growth_mom, margin_last)

        # ===== v2 metrics =====
        forecast3 = _trend_forecast(revs, steps=3)
        forecast_avg = round(sum(forecast3) / len(forecast3), 2) if forecast3 else 0.0
        slope = round(_lin_slope(revs), 2) if n >= 2 else 0.0
        vol = round(_std(revs), 2) if n >= 2 else 0.0

        anomaly_flags: List[str] = []
        if vol > 0 and n >= 2:
            # flag nếu tháng cuối lệch mạnh so với mean
            mean_rev = sum(revs) / n if n else 0.0
            if mean_rev > 0 and abs(rev_last - mean_rev) / mean_rev > 0.6:
                anomaly_flags.append("Doanh thu biến động mạnh")

        # ===== ROI =====
        roi_percent = round((prof_last / cost_last * 100.0), 2) if cost_last > 0 else 0.0

        # ===== Early warning =====
        # Rule:
        # - forecast_avg < revenue_last (dự báo giảm)
        # - growth âm 2 tháng liên tiếp
        # - margin < 5
        early_warning = False
        if n >= 2:
            if forecast_avg < rev_last and growth_mom < 0 and prev_growth_mom < 0 and margin_last < 5:
                early_warning = True

        notes_parts: List[str] = []
        if loss_streak >= 1:
            notes_parts.append(f"Lỗ liên tiếp: {loss_streak}")
        if growth_mom < 0:
            notes_parts.append(f"MoM giảm {abs(growth_mom)}%")
        if margin_last < 5:
            notes_parts.append("Margin thấp")
        if early_warning:
            notes_parts.append("Cảnh báo sớm: nguy cơ giảm doanh thu")

        company_name = ""
        try:
            company_name = getattr(getattr(getattr(s, "brand", None), "company", None), "name", "") or ""
        except Exception:
            company_name = ""

        rows.append(
            ShopHealthRow(
                shop_id=sid,
                shop_name=getattr(s, "name", f"Shop {sid}"),
                platform=getattr(s, "platform", "") or "",
                company_name=company_name,

                months=n,
                last_month=months[-1] if months else "",

                revenue_last=round(rev_last, 2),
                cost_last=round(cost_last, 2),
                profit_last=round(prof_last, 2),
                margin_last=round(margin_last, 2),
                growth_mom=growth_mom,

                stability_score=round(stability, 2),
                margin_score=round(margin_score, 2),
                growth_score=round(growth_score, 2),
                loss_risk_score=round(loss_risk_score, 2),

                health_score=health,
                health_badge=badge,
                risk_level=risk,
                notes="; ".join(notes_parts),

                forecast_next=forecast_avg,
                trend_slope=slope,
                volatility=vol,
                anomaly_flags=anomaly_flags,

                roi_percent=roi_percent,
                early_warning=early_warning,
            )
        )

    # sort: health desc
    rows.sort(key=lambda r: (r.health_score, r.revenue_last), reverse=True)
    return rows