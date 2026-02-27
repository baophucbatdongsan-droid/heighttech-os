# apps/intelligence/services.py
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from django.core.cache import cache
from django.db.models import Sum
from django.db.models.query import QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.intelligence.scoring import ShopHealthRow, compute_shop_health_rows
from apps.performance.models import MonthlyPerformance
from apps.shops.models import Shop


# =====================================================
# JSON SAFE
# =====================================================

def _json_safe(obj: Any) -> Any:
    """
    Convert mọi thứ về JSON-safe:
    - Decimal -> float
    - date/datetime -> isoformat
    - QuerySet -> list
    - dict/list/tuple -> recurse
    """
    if obj is None:
        return None
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, QuerySet):
        return [_json_safe(x) for x in list(obj)]
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


# =====================================================
# HELPERS
# =====================================================

def _has_field(model, field_name: str) -> bool:
    try:
        return any(f.name == field_name for f in model._meta.get_fields())
    except Exception:
        return False


def _safe_month_str(d: Optional[date]) -> str:
    return d.isoformat() if d else ""


def _month_shift(d: date, back: int) -> date:
    """Lùi back tháng (safe, không cần dateutil)."""
    y = d.year
    m = d.month - back
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def _sum_safe(qs, field: str) -> Decimal:
    Model = qs.model
    if not _has_field(Model, field):
        return Decimal("0")
    return qs.aggregate(t=Sum(field))["t"] or Decimal("0")


def _to_float(x: Any) -> float:
    try:
        if x is None:
            return 0.0
        if isinstance(x, Decimal):
            return float(x)
        return float(x)
    except Exception:
        return 0.0


def _trend_forecast(values: List[float], steps: int = 3) -> List[float]:
    """
    Forecast nhẹ: dùng avg delta của 2-3 kỳ gần nhất.
    """
    if not values:
        return [0.0] * steps
    if len(values) == 1:
        return [float(values[-1])] * steps

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


def _serialize_shop_health(rows: List[ShopHealthRow]) -> List[Dict[str, Any]]:
    """
    ✅ Chuẩn hóa ShopHealthRow => list(dict) JSON-safe
    """
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = asdict(r)
        d["anomaly_flags"] = d.get("anomaly_flags") or []
        out.append(_json_safe(d))
    return out


def _build_alerts(rows: List[ShopHealthRow], limit: int = 20) -> List[Dict[str, Any]]:
    """
    Nâng cấp:
    - early_warning => ít nhất P1
    - CRITICAL + HIGH => P0
    """
    alerts: List[Dict[str, Any]] = []

    for r in rows:
        badge = (getattr(r, "health_badge", "") or "").upper()
        risk = (getattr(r, "risk_level", "") or "").upper()

        severity = ""
        if badge == "CRITICAL" and risk == "HIGH":
            severity = "P0"
        elif getattr(r, "early_warning", False):
            severity = "P1"
        elif badge in ("CRITICAL", "WARN") and risk in ("HIGH", "MEDIUM"):
            severity = "P1"
        else:
            continue

        why: List[str] = []
        if getattr(r, "early_warning", False):
            why.append("Cảnh báo sớm: dự báo giảm + tăng trưởng âm + margin thấp")
        if "Lỗ liên tiếp" in (getattr(r, "notes", "") or ""):
            why.append("Lỗ liên tiếp")
        if getattr(r, "growth_mom", 0.0) < 0:
            why.append("MoM giảm")
        if getattr(r, "margin_last", 0.0) < 5:
            why.append("Margin thấp")
        if not why and getattr(r, "notes", ""):
            why.append(getattr(r, "notes", ""))

        alerts.append({
            "severity": severity,
            "shop_id": getattr(r, "shop_id", None),
            "shop_name": getattr(r, "shop_name", "") or "",
            "company_name": getattr(r, "company_name", "") or "",
            "health_score": float(getattr(r, "health_score", 0.0) or 0.0),
            "risk_level": getattr(r, "risk_level", "") or "",
            "health_badge": getattr(r, "health_badge", "") or "",
            "why": why[:3],
        })

    prio = {"P0": 0, "P1": 1}
    alerts.sort(key=lambda x: (prio.get(x.get("severity", ""), 9), x.get("health_score", 999)))
    return alerts[:limit]


def _build_actions(rows: List[ShopHealthRow], limit: int = 15) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    risk_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    rows_sorted = sorted(rows, key=lambda r: (risk_order.get(getattr(r, "risk_level", "LOW"), 9), getattr(r, "health_score", 0.0)))

    for r in rows_sorted[:limit]:
        items: List[str] = []

        if getattr(r, "margin_last", 0.0) < 5:
            items.append("Giảm chi phí ads/đẩy SKU margin cao; kiểm tra phí sàn/voucher.")
            items.append("Tách report theo SKU: SKU nào kéo margin xuống thì stop/đổi giá.")

        if getattr(r, "growth_mom", 0.0) < 0:
            items.append("Kiểm tra traffic & conversion; A/B ảnh bìa + giá + ưu đãi.")
            items.append("Rà lại tồn kho/top keywords; đẩy chiến dịch cho 3 SKU chủ lực.")

        if "Lỗ liên tiếp" in (getattr(r, "notes", "") or ""):
            items.append("Khoanh vùng nguyên nhân lỗ: ads vs vận hành vs hoàn/huỷ.")
            items.append("Đặt guardrail: ROAS tối thiểu; giảm ngân sách nếu dưới ngưỡng.")

        if not items:
            items.append("Duy trì nhịp tăng trưởng: tối ưu ads nhẹ + mở rộng SKU thắng.")

        actions.append({
            "shop_id": getattr(r, "shop_id", None),
            "shop_name": getattr(r, "shop_name", "") or "",
            "company_name": getattr(r, "company_name", "") or "",
            "risk_level": getattr(r, "risk_level", "") or "",
            "health_badge": getattr(r, "health_badge", "") or "",
            "todo": items[:3],
        })

    return actions


# =====================================================
# SERVICE
# =====================================================

class FounderIntelligenceService:
    CACHE_TTL = 60 * 10  # 10 minutes

    @staticmethod
    def _cache_key_founder(month: Optional[str]) -> str:
        return f"founder_ctx:{month or 'all'}"

    @staticmethod
    def _cache_key_shop(shop_id: int, month: Optional[str]) -> str:
        return f"founder_shop_ctx:{shop_id}:{month or 'all'}"

    @staticmethod
    def _base_qs():
        qs = MonthlyPerformance.objects.all()
        if _has_field(MonthlyPerformance, "shop"):
            qs = qs.select_related("shop", "shop__brand", "shop__brand__company")
        elif _has_field(MonthlyPerformance, "company"):
            qs = qs.select_related("company")
        return qs

    @staticmethod
    def _apply_month_filter(qs, month: Optional[str]) -> Tuple[Any, Optional[date]]:
        selected_month: Optional[date] = None
        if month:
            d = parse_date(month)
            if d:
                selected_month = d
                qs = qs.filter(month=d)
        return qs, selected_month

    @staticmethod
    def _kpi_totals(qs) -> Dict[str, Decimal]:
        total_revenue = _sum_safe(qs, "revenue")
        total_profit = _sum_safe(qs, "profit")
        total_net = _sum_safe(qs, "company_net_profit")

        base = total_net if total_net != 0 else total_profit
        margin = Decimal("0")
        if total_revenue > 0:
            margin = (base / total_revenue) * Decimal("100")

        return {
            "total_revenue": total_revenue,
            "total_profit": total_profit,
            "total_net": total_net,
            "margin": margin,
        }

    @staticmethod
    def _company_name_key(model) -> Optional[str]:
        if _has_field(model, "shop"):
            return "shop__brand__company__name"
        if _has_field(model, "company"):
            return "company__name"
        return None

    @staticmethod
    def _top_companies(qs, limit: int = 10):
        Model = qs.model
        key = FounderIntelligenceService._company_name_key(Model)
        if not key or not _has_field(Model, "revenue"):
            return []
        return qs.values(key).annotate(total_revenue=Sum("revenue")).order_by("-total_revenue")[:limit]

    @staticmethod
    def _loss_companies(qs, limit: int = 10):
        Model = qs.model
        key = FounderIntelligenceService._company_name_key(Model)

        metric = None
        if _has_field(Model, "company_net_profit"):
            metric = "company_net_profit"
        elif _has_field(Model, "profit"):
            metric = "profit"

        if not key or not metric:
            return []

        return (
            qs.values(key)
            .annotate(total_metric=Sum(metric))
            .filter(total_metric__lt=0)
            .order_by("total_metric")[:limit]
        )

    @staticmethod
    def _forecast_founder(qs, months_back: int = 6) -> Dict[str, Any]:
        Model = qs.model
        if not (_has_field(Model, "month") and _has_field(Model, "revenue")):
            return {"months": [], "revenues": [], "profits": [], "forecast_next_3": []}

        monthly = (
            qs.values("month")
            .annotate(
                revenue=Sum("revenue"),
                profit=Sum("profit") if _has_field(Model, "profit") else Sum("revenue"),
            )
            .order_by("month")
        )

        months: List[str] = []
        revenues: List[float] = []
        profits: List[float] = []

        for row in monthly:
            m = row.get("month")
            months.append(m.strftime("%m/%Y") if m else "")
            revenues.append(_to_float(row.get("revenue")))
            profits.append(_to_float(row.get("profit")))

        if len(revenues) > months_back:
            months = months[-months_back:]
            revenues = revenues[-months_back:]
            profits = profits[-months_back:]

        forecast_next_3 = _trend_forecast(revenues, steps=3)

        return {
            "months": months,
            "revenues": [round(x, 2) for x in revenues],
            "profits": [round(x, 2) for x in profits],
            "forecast_next_3": forecast_next_3,
        }

    @staticmethod
    def _build_ceo_summary(rows: List[ShopHealthRow], forecast: Dict[str, Any]) -> Dict[str, Any]:
        total = len(rows)
        high_risk = sum(1 for r in rows if (getattr(r, "risk_level", "") or "").upper() == "HIGH")
        neg_growth = sum(1 for r in rows if getattr(r, "growth_mom", 0.0) < 0)
        early_warn = sum(1 for r in rows if getattr(r, "early_warning", False))

        cashflow_trend = "UNKNOWN"
        revs = forecast.get("revenues") or []
        if len(revs) >= 2:
            cashflow_trend = "DOWN" if revs[-1] < revs[-2] else "UP"

        recommendation = "Ổn định."
        if high_risk > 0 or early_warn > 0:
            recommendation = f"Ưu tiên xử lý {max(high_risk, early_warn)} shop rủi ro trước (HIGH / Cảnh báo sớm)."

        return {
            "tong_shop": total,
            "shop_rui_ro_cao": high_risk,
            "shop_tang_truong_am": neg_growth,
            "shop_canh_bao_som": early_warn,
            "xu_huong_doanh_thu": cashflow_trend,
            "goi_y": recommendation,
        }

    # =====================================================
    # PUBLIC API
    # =====================================================

    @staticmethod
    def build_founder_context(month: Optional[str] = None) -> Dict[str, Any]:
        key = FounderIntelligenceService._cache_key_founder(month)
        cached = cache.get(key)
        if cached:
            return cached

        qs = FounderIntelligenceService._base_qs()
        qs, selected_month = FounderIntelligenceService._apply_month_filter(qs, month)
        kpi = FounderIntelligenceService._kpi_totals(qs)

        # ---------- Shop Health ----------
        shop_health_rows: List[ShopHealthRow] = []
        if _has_field(MonthlyPerformance, "shop"):
            today = timezone.now().date()
            first_of_this_month = today.replace(day=1)
            start_month = _month_shift(first_of_this_month, 5)

            shops_qs = Shop.objects.select_related("brand", "brand__company").filter(is_active=True)

            perf_qs = MonthlyPerformance.objects.all()
            if _has_field(MonthlyPerformance, "month"):
                perf_qs = perf_qs.filter(month__gte=start_month, month__lte=first_of_this_month)

            shop_health_rows = compute_shop_health_rows(
                shops_qs=shops_qs,
                perf_qs=perf_qs,
                months_window=6,
            )

            # rank_percentile (0..100) theo health_score (đã sort desc)
            n = len(shop_health_rows)
            if n > 1:
                for idx, r in enumerate(shop_health_rows):
                    pct = 100.0 * (1.0 - (idx / (n - 1)))
                    r.rank_percentile = round(pct, 2)
            elif n == 1:
                shop_health_rows[0].rank_percentile = 100.0

        forecast = FounderIntelligenceService._forecast_founder(qs, months_back=6)
        alerts = _build_alerts(shop_health_rows, limit=20)
        actions = _build_actions(shop_health_rows, limit=15)
        ceo_summary = FounderIntelligenceService._build_ceo_summary(shop_health_rows, forecast)

        # ✅ IMPORTANT: convert KPI + top/loss to JSON-safe (Decimal/QuerySet)
        top_companies = list(FounderIntelligenceService._top_companies(qs))
        loss_companies = list(FounderIntelligenceService._loss_companies(qs))

        data: Dict[str, Any] = {
            "selected_month": _safe_month_str(selected_month),

            # KPI (float để JSON-safe)
            "total_revenue": float(kpi["total_revenue"]),
            "total_profit": float(kpi["total_profit"]),
            "total_net": float(kpi["total_net"]),
            "margin": float(kpi["margin"].quantize(Decimal("0.01"))),

            # tables (list(dict) + Decimal -> float)
            "top_companies": _json_safe(top_companies),
            "loss_companies": _json_safe(loss_companies),

            # scoring (list(dict))
            "shop_health": _serialize_shop_health(shop_health_rows),

            # v2 blocks
            "forecast": _json_safe(forecast),
            "alerts": _json_safe(alerts),
            "actions": _json_safe(actions),

            # CEO mode
            "ceo_summary": _json_safe(ceo_summary),
        }

        # ✅ double-safe: ensure entire payload JSON safe before caching
        data = _json_safe(data)

        cache.set(key, data, timeout=FounderIntelligenceService.CACHE_TTL)
        return data

    @staticmethod
    def build_shop_deep_context(shop, month: Optional[str] = None) -> Dict[str, Any]:
        key = FounderIntelligenceService._cache_key_shop(shop.id, month)
        cached = cache.get(key)
        if cached:
            return cached

        qs = MonthlyPerformance.objects.filter(shop=shop)
        if month and _has_field(MonthlyPerformance, "month"):
            d = parse_date(month)
            if d:
                qs = qs.filter(month=d)

        qs = qs.order_by("-month")

        data: Dict[str, Any] = {
            "shop": shop,
            "items": list(qs[:200]),
            "total_revenue": float(_sum_safe(qs, "revenue")),
            "total_profit": float(_sum_safe(qs, "profit")),
            "total_net": float(_sum_safe(qs, "company_net_profit")),
        }

        # shop/items không json-safe ở đây (vì API layer sẽ serialize),
        # nhưng totals phải safe để tránh command/JSON dump lỗi.
        cache.set(key, data, timeout=FounderIntelligenceService.CACHE_TTL)
        return data