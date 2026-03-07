# FILE: apps/sales/views_client_sales.py
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Optional

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpRequest
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.core.decorators import require_ability
from apps.core.policy import VIEW_DASHBOARD
from apps.sales.models import DailySales, SkuSalesDaily


def _tenant_id(request: HttpRequest) -> Optional[int]:
    tid = getattr(request, "tenant_id", None)
    try:
        if tid:
            return int(tid)
    except Exception:
        pass
    for k in ("tenant_id", "active_tenant_id", "current_tenant_id"):
        try:
            v = request.session.get(k)
            if v:
                return int(v)
        except Exception:
            pass
    return None


@login_required
@require_ability(VIEW_DASHBOARD)
def client_sales_home(request: HttpRequest):
    tid = _tenant_id(request)
    if not tid:
        return redirect("/dashboard/")

    shop_id = (request.GET.get("shop") or "").strip()
    if not shop_id:
        # để demo: nếu chưa chọn shop thì vẫn show tenant-level
        shop_id_int = None
    else:
        try:
            shop_id_int = int(shop_id)
        except Exception:
            shop_id_int = None

    now = timezone.now().date()
    days = int(request.GET.get("days") or 14)
    start = now - timedelta(days=days - 1)

    ds = DailySales.objects.filter(tenant_id=tid, date__gte=start, date__lte=now)
    ssd = SkuSalesDaily.objects.filter(tenant_id=tid, date__gte=start, date__lte=now)

    if shop_id_int:
        ds = ds.filter(shop_id=shop_id_int)
        ssd = ssd.filter(shop_id=shop_id_int)

    daily = list(ds.order_by("date")[:400])

    top_sku = (
        ssd.values("sku")
        .annotate(revenue=Sum("revenue"), orders=Sum("orders"), units=Sum("units"))
        .order_by("-revenue")[:12]
    )

    total_rev = ds.aggregate(v=Sum("revenue"))["v"] or 0
    total_orders = ds.aggregate(v=Sum("orders"))["v"] or 0
    total_spend = ds.aggregate(v=Sum("spend"))["v"] or 0

    context: Dict[str, Any] = {
        "tid": tid,
        "shop": shop_id,
        "days": days,
        "start": start,
        "now": now,
        "daily": daily,
        "top_sku": list(top_sku),
        "kpi_rev": total_rev,
        "kpi_orders": total_orders,
        "kpi_spend": total_spend,
    }
    return render(request, "sales/client_sales_home.html", context)