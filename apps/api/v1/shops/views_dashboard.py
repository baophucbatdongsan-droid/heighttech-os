# apps/api/v1/shops/views_dashboard.py
from __future__ import annotations

from typing import Any, Dict, Optional

from django.apps import apps
from django.db.models import Count
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import AbilityPermission, VIEW_API_DASHBOARD
from apps.api.v1.base import TenantRequiredMixin


def _get_model(app_label: str, model_name: str):
    """
    Safe model loader: không crash nếu model rename / chưa tồn tại.
    """
    try:
        return apps.get_model(app_label, model_name)
    except Exception:
        return None


def _first_existing_model(app_label: str, names: list[str]):
    for n in names:
        m = _get_model(app_label, n)
        if m is not None:
            return m
    return None


class ShopDashboardView(TenantRequiredMixin, APIView):
    """
    GET /api/v1/shops/<shop_id>/dashboard/

    FINAL:
    - Không import cứng Performance (vì codebase anh đang không có model tên đó)
    - Dùng apps.get_model() + fallback để không crash
    - Trả về: shop basic + work counters + (optional) performance summary nếu tìm được model phù hợp
    """
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def get(self, request, shop_id: int):
        tenant = self.get_tenant()

        Shop = _get_model("shops", "Shop")
        WorkItem = _get_model("work", "WorkItem")

        if Shop is None:
            return Response({"ok": False, "message": "Shop model not found"}, status=500)
        if WorkItem is None:
            return Response({"ok": False, "message": "WorkItem model not found"}, status=500)

        shop = Shop.objects_all.filter(id=shop_id, tenant_id=tenant.id).first()
        if not shop:
            return Response({"ok": False, "message": "Shop not found"}, status=404)

        # -------------------------
        # Work counters (by shop_id)
        # -------------------------
        base_qs = WorkItem.objects_all.filter(tenant_id=tenant.id, shop_id=shop.id)

        # group by status
        st_rows = list(base_qs.values("status").annotate(total=Count("id")))
        counts_by_status = {r["status"]: r["total"] for r in st_rows}

        work = {
            "total": base_qs.count(),
            "by_status": {
                "todo": counts_by_status.get("todo", 0),
                "doing": counts_by_status.get("doing", 0),
                "blocked": counts_by_status.get("blocked", 0),
                "done": counts_by_status.get("done", 0),
                "cancelled": counts_by_status.get("cancelled", 0),
            },
        }

        # -------------------------
        # Optional performance summary
        # (tùy codebase: model có thể là MonthlyPerformance, ShopPerformanceDaily,...)
        # -------------------------
        PerformanceModel = _first_existing_model(
            "performance",
            [
                "Performance",
                "MonthlyPerformance",
                "ShopPerformance",
                "ShopDailyPerformance",
                "PerformanceDaily",
                "PerformanceMonthly",
            ],
        )

        performance: Dict[str, Any] = {"available": False}

        if PerformanceModel is not None:
            # cố gắng đoán field shop_id/tenant_id phổ biến
            qs = PerformanceModel.objects_all.all() if hasattr(PerformanceModel, "objects_all") else PerformanceModel.objects.all()

            # filter an toàn theo các field nếu tồn tại
            if hasattr(PerformanceModel, "tenant_id"):
                qs = qs.filter(tenant_id=tenant.id)
            if hasattr(PerformanceModel, "shop_id"):
                qs = qs.filter(shop_id=shop.id)

            # lấy record mới nhất nếu có created_at / date / month
            order_fields = []
            for f in ["date", "month", "created_at", "updated_at", "id"]:
                if hasattr(PerformanceModel, f):
                    order_fields.append(f"-{f}")
                    break

            if order_fields:
                latest = qs.order_by(*order_fields).first()
            else:
                latest = qs.first()

            performance = {
                "available": True,
                "model": PerformanceModel.__name__,
                "latest": None,
            }

            if latest is not None:
                # trả “một ít” field phổ biến, tránh dump toàn bộ
                out: Dict[str, Any] = {"id": getattr(latest, "id", None)}
                for f in ["date", "month", "revenue", "cost", "profit", "orders", "roas", "gmv"]:
                    if hasattr(latest, f):
                        out[f] = getattr(latest, f)
                performance["latest"] = out

        data = {
            "ok": True,
            "shop": {
                "id": shop.id,
                "name": getattr(shop, "name", "") or getattr(shop, "title", "") or "",
                "code": getattr(shop, "code", "") if hasattr(shop, "code") else "",
            },
            "work": work,
            "performance": performance,
        }
        return Response(data)