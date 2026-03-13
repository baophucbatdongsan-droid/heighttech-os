from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.shops.models import Shop
from apps.products.models import Product

def _shop_company_id(x: Shop):
    try:
        brand = getattr(x, "brand", None)
        company = getattr(brand, "company", None) if brand else None
        return getattr(company, "id", None)
    except Exception:
        return None


def _shop_company_name(x: Shop) -> str:
    try:
        brand = getattr(x, "brand", None)
        company = getattr(brand, "company", None) if brand else None
        if company and getattr(company, "name", None):
            return str(company.name)
    except Exception:
        pass
    return ""
def _tenant_id_from_request(request) -> Optional[int]:
    tid = request.headers.get("X-Tenant-Id")
    if tid:
        try:
            return int(tid)
        except Exception:
            pass

    tenant = getattr(request, "tenant", None)
    tid = getattr(tenant, "id", None) if tenant else None
    if tid:
        try:
            return int(tid)
        except Exception:
            pass

    tid = getattr(request, "tenant_id", None)
    if tid:
        try:
            return int(tid)
        except Exception:
            pass

    try:
        user = getattr(request, "user", None)
        membership = (
            user.memberships.filter(is_active=True)
            .order_by("id")
            .first()
        )
        if membership and membership.tenant_id:
            return int(membership.tenant_id)
    except Exception:
        pass

    return None


def _int(v: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if v is None:
            return default
        s = str(v).strip().replace(",", "")
        if s == "":
            return default
        return int(float(s))
    except Exception:
        return default


def _dec(v: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        if v is None:
            return default
        s = str(v).strip().replace(",", "")
        if s == "":
            return default
        return Decimal(s)
    except Exception:
        return default


def _serialize_shop(x: Shop) -> Dict[str, Any]:
    return {
        "id": x.id,
        "tenant_id": x.tenant_id,
        "company_id": _shop_company_id(x),
        "company_name": _shop_company_name(x),
        "name": x.name,
        "code": getattr(x, "code", "") or "",
        "platform": getattr(x, "platform", "") or "",
        "industry_code": getattr(x, "industry_code", "") or "",
        "is_active": getattr(x, "is_active", True),
    }


def _product_category(x: Product) -> str:
    meta = getattr(x, "meta", None) or {}
    for key in ["category", "category_name", "group_name", "product_category"]:
        val = meta.get(key)
        if val:
            return str(val)
    return "-"


def _orders_7d(x: Product) -> int:
    meta = getattr(x, "meta", None) or {}
    return int(meta.get("orders_7d") or 0)


def _revenue_7d(x: Product) -> Decimal:
    meta = getattr(x, "meta", None) or {}
    raw = meta.get("revenue_7d")
    if raw not in [None, ""]:
        try:
            return Decimal(str(raw))
        except Exception:
            pass
    return Decimal(str(_orders_7d(x))) * Decimal(str(x.price or 0))


def _serialize_sku(x: Product) -> Dict[str, Any]:
    company_name = ""
    shop_name = ""

    try:
        company = getattr(x, "company", None)
        if company and getattr(company, "name", None):
            company_name = str(company.name)
    except Exception:
        pass

    try:
        shop = getattr(x, "shop", None)
        if shop and getattr(shop, "name", None):
            shop_name = str(shop.name)
    except Exception:
        pass

    return {
        "id": x.id,
        "tenant_id": x.tenant_id,
        "company_id": x.company_id,
        "company_name": company_name,
        "shop_id": x.shop_id,
        "shop_name": shop_name,
        "sku_code": x.sku,
        "name": x.name,
        "category": _product_category(x),
        "price": str(x.price or 0),
        "cost_price": str(x.cost or 0),
        "stock": int(x.stock or 0),
        "status": x.status or "active",
        "orders_7d": _orders_7d(x),
        "revenue_7d": str(_revenue_7d(x)),
        "meta": x.meta or {},
    }


class ShopListApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Không xác định được tenant"}, status=400)

        keyword = str(request.GET.get("q") or "").strip()

        qs = Shop.objects_all.filter(tenant_id=int(tenant_id)).select_related("brand").order_by("name", "id")

        if keyword:
            qs = qs.filter(
                Q(name__icontains=keyword) |
                Q(code__icontains=keyword)
            )

        items = [_serialize_shop(x) for x in qs[:500]]
        return Response({"ok": True, "items": items, "count": len(items)})


class ShopCreateApi(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        return Response(
            {
                "ok": False,
                "message": "ShopCreateApi đang dùng flow workspace riêng, không tạo trực tiếp tại đây."
            },
            status=400,
        )


class ShopSkuListApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response(
                {"ok": False, "message": "Không xác định được tenant", "items": []},
                status=400,
            )

        keyword = str(request.GET.get("q") or "").strip()
        company_id = _int(request.GET.get("company_id"))
        shop_id = _int(request.GET.get("shop_id"))

        qs = (
            Product.objects_all
            .filter(tenant_id=int(tenant_id))
            .select_related("shop", "company")
            .order_by("-id")
        )

        if company_id is not None:
            qs = qs.filter(company_id=int(company_id))
        if shop_id is not None:
            qs = qs.filter(shop_id=int(shop_id))

        if keyword:
            qs = qs.filter(
                Q(name__icontains=keyword) |
                Q(sku__icontains=keyword) |
                Q(status__icontains=keyword)
            )

        items = [_serialize_sku(x) for x in qs[:500]]
        return Response({"ok": True, "items": items, "count": len(items)})


class ShopSkuCreateApi(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Không xác định được tenant"}, status=400)

        data = request.data or {}

        company_id = _int(data.get("company_id"))
        shop_id = _int(data.get("shop_id"))
        sku_code = str(data.get("sku_code") or "").strip()
        name = str(data.get("name") or "").strip()
        category = str(data.get("category") or "").strip()
        price = _dec(data.get("price"))
        cost_price = _dec(data.get("cost_price"))
        stock = _int(data.get("stock"), 0) or 0

        if not company_id:
            return Response({"ok": False, "message": "Thiếu company_id"}, status=400)
        if not shop_id:
            return Response({"ok": False, "message": "Thiếu shop_id"}, status=400)
        if not sku_code:
            return Response({"ok": False, "message": "Thiếu sku_code"}, status=400)
        if not name:
            return Response({"ok": False, "message": "Thiếu tên sản phẩm"}, status=400)

        shop = Shop.objects_all.filter(
            id=int(shop_id),
            tenant_id=int(tenant_id),
        ).first()
        if not shop:
            return Response({"ok": False, "message": "Shop không tồn tại trong tenant hiện tại"}, status=400)

        shop_company_id = _shop_company_id(shop)
        if company_id and shop_company_id and int(company_id) != int(shop_company_id):
            return Response({"ok": False, "message": "Shop không thuộc company đã chọn"}, status=400)

        exists = Product.objects_all.filter(
            tenant_id=int(tenant_id),
            shop_id=int(shop_id),
            sku=sku_code,
        ).first()
        if exists:
            return Response({"ok": False, "message": "SKU đã tồn tại trong shop này"}, status=400)

        meta = {}
        if category:
            meta["category"] = category
            meta["category_name"] = category
        meta["orders_7d"] = 0
        meta["revenue_7d"] = "0"

        obj = Product.objects.create(
            tenant_id=int(tenant_id),
            company_id=int(company_id),
            shop_id=int(shop_id),
            sku=sku_code,
            name=name,
            price=price,
            cost=cost_price,
            stock=int(stock),
            status="active",
            meta=meta,
        )

        return Response({"ok": True, "item": _serialize_sku(obj)}, status=201)