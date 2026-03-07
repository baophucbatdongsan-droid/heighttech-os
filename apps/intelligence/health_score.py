# apps/intelligence/health_score.py
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Optional

from django.apps import apps
from django.db.models import Count, Q
from django.utils import timezone

from .health_rules import compute_weighted_score


def _get_model(app_label: str, model_name: str):
    try:
        return apps.get_model(app_label, model_name)
    except Exception:
        return None


def _safe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def _collect_work_metrics(tenant_id: int, shop_id: int) -> Dict[str, Optional[float]]:
    WorkItem = _get_model("work", "WorkItem")
    if not WorkItem:
        return {"overdue_tasks": None, "blocked_tasks": None, "backlog_open_tasks": None}

    now = timezone.now()
    qs = WorkItem.objects_all.filter(tenant_id=tenant_id, shop_id=shop_id)

    overdue = (
        qs.filter(due_at__isnull=False, due_at__lt=now)
        .exclude(status__in=["done", "cancelled"])
        .count()
    )
    blocked = qs.filter(status="blocked").count()
    backlog = qs.exclude(status__in=["done", "cancelled"]).count()

    return {
        "overdue_tasks": float(overdue),
        "blocked_tasks": float(blocked),
        "backlog_open_tasks": float(backlog),
    }


def _collect_inventory_metrics(tenant_id: int, shop_id: int) -> Dict[str, Optional[float]]:
    """
    Inventory module có/không tuỳ codebase => dùng get_model + fail-soft.
    Nếu anh có model Inventory/SkuStock khác tên, mình chỉnh mapping sau 30s.
    """
    # common candidates
    Stock = _get_model("shops", "ShopStock") or _get_model("inventory", "Stock") or _get_model("inventory", "SkuStock")
    if not Stock:
        return {"low_stock_skus": None}

    # heuristic fields
    qty_field = "quantity" if hasattr(Stock, "quantity") else ("qty" if hasattr(Stock, "qty") else None)
    if not qty_field:
        return {"low_stock_skus": None}

    threshold = 5  # v1 default
    try:
        q = {f"{qty_field}__lte": threshold}
        low_cnt = Stock.objects_all.filter(tenant_id=tenant_id, shop_id=shop_id, **q).count()
        return {"low_stock_skus": float(low_cnt)}
    except Exception:
        return {"low_stock_skus": None}


def _collect_performance_metrics(tenant_id: int, shop_id: int) -> Dict[str, Optional[float]]:
    """
    Performance có thể ở apps.performance.models -> nhiều codebase đặt khác.
    Mình dò 2-3 tên phổ biến và fallback None.
    """
    Perf = _get_model("performance", "Performance") or _get_model("performance", "DailyPerformance") or _get_model("performance", "ShopPerformance")
    if not Perf:
        return {"roas_7d": None, "revenue_7d": None, "orders_7d": None}

    now = timezone.now()
    since = now - timedelta(days=7)

    # heuristic fields
    date_field = "date" if hasattr(Perf, "date") else ("day" if hasattr(Perf, "day") else None)
    if not date_field:
        return {"roas_7d": None, "revenue_7d": None, "orders_7d": None}

    # values fields
    roas_field = "roas" if hasattr(Perf, "roas") else None
    revenue_field = "revenue" if hasattr(Perf, "revenue") else ("gmv" if hasattr(Perf, "gmv") else None)
    orders_field = "orders" if hasattr(Perf, "orders") else ("order_count" if hasattr(Perf, "order_count") else None)

    filters = {f"{date_field}__gte": since.date() if "date" in date_field else since}
    try:
        qs = Perf.objects_all.filter(tenant_id=tenant_id, shop_id=shop_id, **filters)

        # simplest: take latest row in 7d window and also sum revenue/orders
        latest = qs.order_by(f"-{date_field}").first()
        roas_7d = _safe_float(getattr(latest, roas_field, None)) if (latest and roas_field) else None

        revenue_7d = None
        if revenue_field:
            try:
                revenue_7d = _safe_float(qs.values(revenue_field).aggregate(x=Count("id")) and None)  # noop, keep safe
            except Exception:
                revenue_7d = None
            # better: sum() via python (safe cross-field types)
            try:
                revenue_7d = float(sum(float(getattr(r, revenue_field) or 0) for r in qs.only(revenue_field)))
            except Exception:
                pass

        orders_7d = None
        if orders_field:
            try:
                orders_7d = float(sum(float(getattr(r, orders_field) or 0) for r in qs.only(orders_field)))
            except Exception:
                pass

        return {"roas_7d": roas_7d, "revenue_7d": revenue_7d, "orders_7d": orders_7d}
    except Exception:
        return {"roas_7d": None, "revenue_7d": None, "orders_7d": None}


def compute_shop_health(tenant_id: int, shop_id: int) -> Dict[str, Any]:
    """
    ONE CALL = all metrics + final score + alerts.
    """
    metrics: Dict[str, Optional[float]] = {}
    metrics.update(_collect_performance_metrics(tenant_id, shop_id))
    metrics.update(_collect_work_metrics(tenant_id, shop_id))
    metrics.update(_collect_inventory_metrics(tenant_id, shop_id))

    scored = compute_weighted_score(metrics)

    alerts = []
    score = int(scored["score"])
    level = str(scored["level"])

    if level in {"warning", "critical"}:
        alerts.append({"severity": level, "message": f"Shop health {score}/100 ({level})"})

    # specific alerts
    if (metrics.get("roas_7d") is not None) and (metrics["roas_7d"] < 1.2):
        alerts.append({"severity": "warning", "message": f"ROAS thấp: {metrics['roas_7d']}"})
    if (metrics.get("overdue_tasks") is not None) and (metrics["overdue_tasks"] >= 5):
        alerts.append({"severity": "warning", "message": f"Overdue tasks nhiều: {int(metrics['overdue_tasks'])}"})
    if (metrics.get("blocked_tasks") is not None) and (metrics["blocked_tasks"] >= 3):
        alerts.append({"severity": "warning", "message": f"Blocked tasks nhiều: {int(metrics['blocked_tasks'])}"})
    if (metrics.get("low_stock_skus") is not None) and (metrics["low_stock_skus"] >= 5):
        alerts.append({"severity": "warning", "message": f"Low stock SKUs: {int(metrics['low_stock_skus'])}"})

    return {
        "tenant_id": int(tenant_id),
        "shop_id": int(shop_id),
        "metrics": metrics,
        "score": scored,
        "alerts": alerts,
        "generated_at": timezone.now().isoformat(),
    }