from __future__ import annotations

from typing import Any, Dict

from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.shops.models import Shop
from apps.brands.models import Brand


def _tenant_id_from_request(request):
    tid = request.headers.get("X-Tenant-Id")
    if tid:
        try:
            return int(tid)
        except Exception:
            pass

    try:
        from apps.accounts.models import Membership
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            m = (
                Membership.objects.filter(user=user, is_active=True)
                .order_by("id")
                .first()
            )
            if m and m.tenant_id:
                return int(m.tenant_id)
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


def _serialize_shop(x: Shop) -> Dict[str, Any]:
    brand_name = ""
    try:
        brand_name = getattr(x.brand, "name", "") if getattr(x, "brand", None) else ""
    except Exception:
        brand_name = ""

    return {
        "id": x.id,
        "tenant_id": x.tenant_id,
        "brand_id": x.brand_id,
        "brand_name": brand_name,
        "name": x.name,
        "platform": x.platform or "",
        "code": x.code or "",
        "description": x.description or "",
        "status": x.status or "",
        "industry_code": x.industry_code or "",
        "rule_version": x.rule_version or "",
        "started_at": x.started_at.isoformat() if x.started_at else None,
        "ended_at": x.ended_at.isoformat() if x.ended_at else None,
        "is_active": bool(x.is_active),
        "created_at": x.created_at.isoformat() if x.created_at else None,
        "updated_at": x.updated_at.isoformat() if x.updated_at else None,
    }


class ShopListApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        q = str(request.GET.get("q") or "").strip()

        qs = (
            Shop.objects_all
            .filter(tenant_id=int(tenant_id))
            .select_related("brand")
            .order_by("-updated_at", "-id")
        )

        if q:
            qs = qs.filter(
                Q(name__icontains=q) |
                Q(code__icontains=q) |
                Q(platform__icontains=q) |
                Q(brand__name__icontains=q)
            )

        items = [_serialize_shop(x) for x in qs[:100]]

        return Response({
            "ok": True,
            "items": items,
        })


class ShopCreateApi(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        data = request.data or {}

        name = str(data.get("name") or "").strip()
        brand_id = _int_or_none(data.get("brand_id"))
        platform = str(data.get("platform") or "").strip()
        code = str(data.get("code") or "").strip()
        description = str(data.get("description") or "").strip()
        status = str(data.get("status") or Shop.STATUS_ACTIVE).strip()
        industry_code = str(data.get("industry_code") or "default").strip() or "default"
        rule_version = str(data.get("rule_version") or "v1").strip() or "v1"

        if not name:
            return Response({"ok": False, "message": "Thiếu tên shop"}, status=400)

        if not brand_id:
            return Response({"ok": False, "message": "Thiếu Brand ID"}, status=400)

        brand = (
            Brand.objects
            .filter(id=int(brand_id), tenant_id=int(tenant_id))
            .first()
        )
        if not brand:
            return Response(
                {"ok": False, "message": "Brand không tồn tại trong tenant hiện tại"},
                status=400
            )

        allowed_status = {x[0] for x in Shop.STATUS_CHOICES}
        if status not in allowed_status:
            status = Shop.STATUS_ACTIVE

        obj = Shop.objects_all.create(
            tenant_id=int(tenant_id),
            brand_id=brand.id,
            name=name,
            platform=platform or None,
            code=code or None,
            description=description or None,
            status=status,
            industry_code=industry_code,
            rule_version=rule_version,
            is_active=(status == Shop.STATUS_ACTIVE),
        )

        obj = Shop.objects_all.select_related("brand").get(id=obj.id)

        return Response({
            "ok": True,
            "item": _serialize_shop(obj),
        }, status=201)