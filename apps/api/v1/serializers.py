# apps/api/v1/serializers.py
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict


def _to_float(x: Any) -> float:
    try:
        if x is None:
            return 0.0
        if isinstance(x, Decimal):
            return float(x)
        return float(x)
    except Exception:
        return 0.0


def _to_str_date(x: Any) -> str:
    try:
        if isinstance(x, (date, datetime)):
            return x.isoformat()
        return str(x) if x is not None else ""
    except Exception:
        return ""


def _get(row: Any, key: str, default=None):
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def serialize_shop(shop) -> Dict[str, Any]:
    if not shop:
        return {}
    return {
        "id": getattr(shop, "id", None),
        "name": getattr(shop, "name", "") or "",
        "platform": getattr(shop, "platform", "") or "",
        "brand_id": getattr(shop, "brand_id", None),
    }


def serialize_monthly_performance(mp) -> Dict[str, Any]:
    if not mp:
        return {}

    def g(name: str, default=None):
        return getattr(mp, name, default)

    return {
        "id": g("id"),
        "month": _to_str_date(g("month")),
        "shop_id": g("shop_id"),
        "company_id": g("company_id"),
        "revenue": _to_float(g("revenue")),
        "cost": _to_float(g("cost")),
        "profit": _to_float(g("profit")),
        "company_net_profit": _to_float(g("company_net_profit")),
    }


def serialize_shop_health_row(row: Any) -> Dict[str, Any]:
    """
    ✅ Accept:
      - dataclass ShopHealthRow
      - dict (services đã serialize)
      - object attributes
    """
    if row is None:
        return {}

    if is_dataclass(row):
        row = asdict(row)

    return {
        "shop_id": _get(row, "shop_id"),
        "shop_name": _get(row, "shop_name", "") or "",
        "platform": _get(row, "platform", "") or "",
        "company_name": _get(row, "company_name", "") or "",
        "months": int(_get(row, "months", 0) or 0),
        "last_month": _get(row, "last_month", "") or "",
        "revenue_last": _to_float(_get(row, "revenue_last")),
        "cost_last": _to_float(_get(row, "cost_last")),
        "profit_last": _to_float(_get(row, "profit_last")),
        "margin_last": _to_float(_get(row, "margin_last")),
        "growth_mom": _to_float(_get(row, "growth_mom")),
        "stability_score": _to_float(_get(row, "stability_score")),
        "margin_score": _to_float(_get(row, "margin_score")),
        "growth_score": _to_float(_get(row, "growth_score")),
        "loss_risk_score": _to_float(_get(row, "loss_risk_score")),
        "health_score": _to_float(_get(row, "health_score")),
        "health_badge": (_get(row, "health_badge", "UNKNOWN") or "UNKNOWN"),
        "risk_level": (_get(row, "risk_level", "LOW") or "LOW"),
        "notes": _get(row, "notes", "") or "",
        # v2
        "forecast_next": _to_float(_get(row, "forecast_next")),
        "trend_slope": _to_float(_get(row, "trend_slope")),
        "volatility": _to_float(_get(row, "volatility")),
        "anomaly_flags": _get(row, "anomaly_flags", []) or [],
        "rank_percentile": _to_float(_get(row, "rank_percentile")),
        # v3
        "roi_percent": _to_float(_get(row, "roi_percent")),
        "early_warning": bool(_get(row, "early_warning", False)),
    }