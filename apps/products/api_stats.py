from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.insight import _get_tenant_id
from apps.products.models import Product
from apps.products.models_stats import ProductDailyStat


def _to_decimal(v: Any) -> Decimal:
    try:
        return Decimal(str(v or 0).strip())
    except Exception:
        return Decimal("0")


def _to_int(v: Any) -> int:
    try:
        return int(str(v or 0).strip())
    except Exception:
        return 0


class ProductDailyStatUpsertApi(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        tenant_id = _get_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        shop_id = request.data.get("shop_id")
        sku = str(request.data.get("sku") or "").strip()
        stat_date = request.data.get("stat_date") or timezone.localdate().isoformat()

        if not shop_id:
            return Response({"ok": False, "message": "Thiếu shop_id"}, status=400)
        if not sku:
            return Response({"ok": False, "message": "Thiếu sku"}, status=400)

        try:
            product = Product.objects_all.get(
                tenant_id=int(tenant_id),
                shop_id=int(shop_id),
                sku=sku,
            )
        except Product.DoesNotExist:
            return Response(
                {
                    "ok": False,
                    "message": f"Không tìm thấy product theo sku={sku} của shop_id={shop_id}",
                },
                status=404,
            )

        units_sold = _to_int(request.data.get("units_sold"))
        orders_count = _to_int(request.data.get("orders_count"))
        revenue = _to_decimal(request.data.get("revenue"))
        ads_spend = _to_decimal(request.data.get("ads_spend"))
        booking_cost = _to_decimal(request.data.get("booking_cost"))
        livestream_revenue = _to_decimal(request.data.get("livestream_revenue"))

        cost_of_goods = _to_decimal(product.cost) * Decimal(units_sold)
        profit_estimate = revenue - cost_of_goods - ads_spend - booking_cost

        if ads_spend > 0:
            roas_estimate = revenue / ads_spend
        else:
            roas_estimate = Decimal("0")

        obj, created = ProductDailyStat.objects_all.update_or_create(
            tenant_id=int(tenant_id),
            shop_id=int(shop_id),
            product_id=product.id,
            stat_date=stat_date,
            defaults={
                "company_id": product.company_id,
                "units_sold": units_sold,
                "orders_count": orders_count,
                "revenue": revenue,
                "cost_of_goods": cost_of_goods,
                "ads_spend": ads_spend,
                "booking_cost": booking_cost,
                "livestream_revenue": livestream_revenue,
                "profit_estimate": profit_estimate,
                "roas_estimate": roas_estimate,
                "meta": {
                    "source": "manual_api",
                    "sku": sku,
                },
            },
        )

        return Response(
            {
                "ok": True,
                "created": created,
                "item": {
                    "id": obj.id,
                    "tenant_id": int(tenant_id),
                    "shop_id": int(shop_id),
                    "product_id": product.id,
                    "sku": product.sku,
                    "name": product.name,
                    "stat_date": str(obj.stat_date),
                    "units_sold": obj.units_sold,
                    "orders_count": obj.orders_count,
                    "revenue": str(obj.revenue),
                    "cost_of_goods": str(obj.cost_of_goods),
                    "ads_spend": str(obj.ads_spend),
                    "booking_cost": str(obj.booking_cost),
                    "livestream_revenue": str(obj.livestream_revenue),
                    "profit_estimate": str(obj.profit_estimate),
                    "roas_estimate": str(obj.roas_estimate),
                },
            }
        )