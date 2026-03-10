# apps/api/v1/os_admin.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from django.apps import apps
from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


def _get_model(app_label: str, model_name: str):
    try:
        return apps.get_model(app_label, model_name)
    except Exception:
        return None


def _has_field(Model, field_name: str) -> bool:
    try:
        Model._meta.get_field(field_name)
        return True
    except Exception:
        return False


def _tenant_id_from_request(request) -> Optional[int]:
    tid = getattr(request, "tenant_id", None)

    if not tid:
        tenant = getattr(request, "tenant", None)
        tid = getattr(tenant, "id", None) if tenant else None

    if not tid:
        try:
            tid = request.headers.get("X-Tenant-Id")
        except Exception:
            tid = None

    try:
        return int(tid) if tid else None
    except Exception:
        return None


def _int_or_none(v):
    try:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        return int(s)
    except Exception:
        return None


def _dec_or_zero(v) -> Decimal:
    try:
        if v in (None, ""):
            return Decimal("0")
        return Decimal(str(v))
    except Exception:
        return Decimal("0")


def _set_if_has(obj, field_name: str, value):
    try:
        obj._meta.get_field(field_name)
        setattr(obj, field_name, value)
        return True
    except Exception:
        return False


def _serialize_shop(x) -> Dict[str, Any]:
    return {
        "id": getattr(x, "id", None),
        "tenant_id": getattr(x, "tenant_id", None),
        "company_id": getattr(x, "company_id", None),
        "name": getattr(x, "name", "") or getattr(x, "title", "") or "",
        "platform": getattr(x, "platform", "") or "",
        "shop_code": getattr(x, "shop_code", "") or "",
        "external_shop_id": getattr(x, "external_shop_id", "") or "",
        "manager_name": getattr(x, "manager_name", "") or "",
        "status": getattr(x, "status", "") or "",
        "created_at": getattr(x, "created_at", None).isoformat() if getattr(x, "created_at", None) else None,
        "updated_at": getattr(x, "updated_at", None).isoformat() if getattr(x, "updated_at", None) else None,
    }


def _serialize_sku(x) -> Dict[str, Any]:
    name = ""
    if hasattr(x, "name"):
        name = getattr(x, "name", "") or ""
    elif hasattr(x, "title"):
        name = getattr(x, "title", "") or ""

    sku = getattr(x, "sku", "") or getattr(x, "code", "") or ""

    category = ""
    if hasattr(x, "category_name"):
        category = getattr(x, "category_name", "") or ""
    elif hasattr(x, "category"):
        category = str(getattr(x, "category", "") or "")

    cost = None
    for f in ("cost_price", "cost", "cost_estimate"):
        if hasattr(x, f):
            cost = getattr(x, f, None)
            break

    price = None
    for f in ("price", "sale_price", "retail_price"):
        if hasattr(x, f):
            price = getattr(x, f, None)
            break

    stock = None
    if hasattr(x, "stock"):
        stock = getattr(x, "stock", None)

    return {
        "id": getattr(x, "id", None),
        "tenant_id": getattr(x, "tenant_id", None),
        "company_id": getattr(x, "company_id", None),
        "shop_id": getattr(x, "shop_id", None),
        "sku": sku,
        "name": name,
        "category": category,
        "price": str(price or 0),
        "cost": str(cost or 0),
        "stock": stock if stock is not None else 0,
        "created_at": getattr(x, "created_at", None).isoformat() if getattr(x, "created_at", None) else None,
        "updated_at": getattr(x, "updated_at", None).isoformat() if getattr(x, "updated_at", None) else None,
    }


class OSShopAdminListCreateApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        Shop = _get_model("shops", "Shop")
        if not Shop:
            return Response({"ok": False, "message": "Không tìm thấy model Shop"}, status=500)

        company_id = _int_or_none(request.GET.get("company_id"))
        q = (request.GET.get("q") or "").strip()

        qs = Shop.objects_all.filter(tenant_id=tenant_id).order_by("-id")

        if company_id and _has_field(Shop, "company"):
            qs = qs.filter(company_id=company_id)

        if q:
            q_filter = Q()
            for f in ("name", "title", "shop_code", "external_shop_id", "platform", "manager_name"):
                if _has_field(Shop, f):
                    q_filter |= Q(**{f"{f}__icontains": q})
            if str(q_filter) != "(AND: )":
                qs = qs.filter(q_filter)

        items = [_serialize_shop(x) for x in qs[:100]]

        return Response(
            {
                "ok": True,
                "tenant_id": tenant_id,
                "count": len(items),
                "items": items,
            }
        )

    def post(self, request):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        Shop = _get_model("shops", "Shop")
        Company = _get_model("companies", "Company")

        if not Shop:
            return Response({"ok": False, "message": "Không tìm thấy model Shop"}, status=500)

        data = request.data or {}

        name = str(data.get("name") or "").strip()
        company_id = _int_or_none(data.get("company_id"))
        platform = str(data.get("platform") or "").strip()
        shop_code = str(data.get("shop_code") or "").strip()
        external_shop_id = str(data.get("external_shop_id") or "").strip()
        manager_name = str(data.get("manager_name") or "").strip()
        status = str(data.get("status") or "active").strip().lower()

        if not name:
            return Response({"ok": False, "message": "Thiếu tên shop"}, status=400)

        if company_id and Company:
            company = Company.objects_all.filter(id=company_id, tenant_id=tenant_id).first()
            if not company:
                return Response({"ok": False, "message": "Company không thuộc tenant hiện tại"}, status=400)

        obj = Shop()
        if _has_field(Shop, "tenant"):
            obj.tenant_id = tenant_id

        if company_id and _has_field(Shop, "company"):
            obj.company_id = company_id

        if _has_field(Shop, "name"):
            obj.name = name
        elif _has_field(Shop, "title"):
            obj.title = name

        _set_if_has(obj, "platform", platform)
        _set_if_has(obj, "shop_code", shop_code)
        _set_if_has(obj, "external_shop_id", external_shop_id)
        _set_if_has(obj, "manager_name", manager_name)
        _set_if_has(obj, "status", status)

        if _has_field(Shop, "is_active") and not hasattr(obj, "status"):
            obj.is_active = True

        # chống trùng mềm
        dup_qs = Shop.objects_all.filter(tenant_id=tenant_id)
        if company_id and _has_field(Shop, "company"):
            dup_qs = dup_qs.filter(company_id=company_id)

        if shop_code and _has_field(Shop, "shop_code") and dup_qs.filter(shop_code=shop_code).exists():
            return Response({"ok": False, "message": "shop_code đã tồn tại"}, status=400)

        if external_shop_id and _has_field(Shop, "external_shop_id") and dup_qs.filter(external_shop_id=external_shop_id).exists():
            return Response({"ok": False, "message": "external_shop_id đã tồn tại"}, status=400)

        obj.save()

        return Response(
            {
                "ok": True,
                "item": _serialize_shop(obj),
            },
            status=201,
        )


class OSSKUAdminListCreateApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        Product = _get_model("products", "Product")
        if not Product:
            return Response({"ok": False, "message": "Không tìm thấy model Product"}, status=500)

        company_id = _int_or_none(request.GET.get("company_id"))
        shop_id = _int_or_none(request.GET.get("shop_id"))
        q = (request.GET.get("q") or "").strip()

        qs = Product.objects_all.filter(tenant_id=tenant_id).order_by("-id")

        if company_id and _has_field(Product, "company"):
            qs = qs.filter(company_id=company_id)

        if shop_id and _has_field(Product, "shop"):
            qs = qs.filter(shop_id=shop_id)

        if q:
            q_filter = Q()
            for f in ("sku", "code", "name", "title", "category_name"):
                if _has_field(Product, f):
                    q_filter |= Q(**{f"{f}__icontains": q})
            if str(q_filter) != "(AND: )":
                qs = qs.filter(q_filter)

        items = [_serialize_sku(x) for x in qs[:100]]

        return Response(
            {
                "ok": True,
                "tenant_id": tenant_id,
                "count": len(items),
                "items": items,
            }
        )

    def post(self, request):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        Product = _get_model("products", "Product")
        Company = _get_model("companies", "Company")
        Shop = _get_model("shops", "Shop")

        if not Product:
            return Response({"ok": False, "message": "Không tìm thấy model Product"}, status=500)

        data = request.data or {}

        company_id = _int_or_none(data.get("company_id"))
        shop_id = _int_or_none(data.get("shop_id"))
        sku = str(data.get("sku") or "").strip()
        name = str(data.get("name") or "").strip()
        category = str(data.get("category") or "").strip()
        price = _dec_or_zero(data.get("price"))
        cost = _dec_or_zero(data.get("cost"))
        stock = _int_or_none(data.get("stock")) or 0

        if not sku:
            return Response({"ok": False, "message": "Thiếu mã SKU"}, status=400)

        if not name:
            return Response({"ok": False, "message": "Thiếu tên sản phẩm"}, status=400)

        if company_id and Company:
            company = Company.objects_all.filter(id=company_id, tenant_id=tenant_id).first()
            if not company:
                return Response({"ok": False, "message": "Company không thuộc tenant hiện tại"}, status=400)

        if shop_id and Shop:
            shop = Shop.objects_all.filter(id=shop_id, tenant_id=tenant_id).first()
            if not shop:
                return Response({"ok": False, "message": "Shop không thuộc tenant hiện tại"}, status=400)

        dup_qs = Product.objects_all.filter(tenant_id=tenant_id)

        if company_id and _has_field(Product, "company"):
            dup_qs = dup_qs.filter(company_id=company_id)

        if shop_id and _has_field(Product, "shop"):
            dup_qs = dup_qs.filter(shop_id=shop_id)

        if _has_field(Product, "sku") and dup_qs.filter(sku=sku).exists():
            return Response({"ok": False, "message": "SKU đã tồn tại trong phạm vi hiện tại"}, status=400)

        if _has_field(Product, "code") and not _has_field(Product, "sku") and dup_qs.filter(code=sku).exists():
            return Response({"ok": False, "message": "Mã sản phẩm đã tồn tại"}, status=400)

        obj = Product()

        if _has_field(Product, "tenant"):
            obj.tenant_id = tenant_id

        if company_id and _has_field(Product, "company"):
            obj.company_id = company_id

        if shop_id and _has_field(Product, "shop"):
            obj.shop_id = shop_id

        if _has_field(Product, "sku"):
            obj.sku = sku
        elif _has_field(Product, "code"):
            obj.code = sku

        if _has_field(Product, "name"):
            obj.name = name
        elif _has_field(Product, "title"):
            obj.title = name

        _set_if_has(obj, "category_name", category)
        _set_if_has(obj, "category", category)
        _set_if_has(obj, "price", price)
        _set_if_has(obj, "sale_price", price)
        _set_if_has(obj, "retail_price", price)
        _set_if_has(obj, "cost_price", cost)
        _set_if_has(obj, "cost", cost)
        _set_if_has(obj, "stock", stock)
        _set_if_has(obj, "is_active", True)

        obj.save()

        return Response(
            {
                "ok": True,
                "item": _serialize_sku(obj),
            },
            status=201,
        )