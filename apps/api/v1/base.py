# apps/api/v1/base.py
from __future__ import annotations

from typing import Any, Dict, Optional

from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.tenant_context import get_current_tenant_id


# =========================
# Response helpers (FINAL + COMPAT)
# =========================
_RESERVED_KEYS = {"ok", "data", "meta", "code", "message", "error"}


def api_ok(
    data: Any = None,
    meta: Optional[Dict[str, Any]] = None,
    status: int = 200,
) -> Response:
    """
    Chuẩn response:
      {
        "ok": true,
        "data": <any>,
        "meta": {...} (optional),

        # COMPAT mirror keys (nếu data là dict)
        "items": ...,
        "item": ...,
        ...
      }

    - Tests của bạn đang dùng res.json()["data"] => luôn có "data".
    - FE cũ có thể đang đọc items/item ở top-level => mirror keys lên root.
    - Không cho mirror đè các key hệ thống.
    """
    payload: Dict[str, Any] = {"ok": True, "data": data}

    if meta is not None:
        payload["meta"] = meta

    # Backward-compat: mirror dict keys lên root (không đè key hệ thống)
    if isinstance(data, dict):
        for k, v in data.items():
            if k in _RESERVED_KEYS:
                continue
            payload.setdefault(k, v)

    return Response(payload, status=status)


def api_error(
    code: str,
    message: str,
    status: int = 400,
    extra: Optional[Dict[str, Any]] = None,
) -> Response:
    """
    Chuẩn error response:
      {
        "ok": false,
        "code": "...",
        "message": "...",
        "data": null,
        "error": {"code": "...", "message": "..."},
        ...extra (không override reserved keys)
      }
    """
    payload: Dict[str, Any] = {
        "ok": False,
        "code": code,
        "message": message,
        "data": None,  # ✅ FINAL: luôn có data để FE/test không lệch schema
        "error": {"code": code, "message": message},
    }

    if extra:
        for k, v in extra.items():
            if k in _RESERVED_KEYS:
                continue
            payload[k] = v

    return Response(payload, status=status)


# =========================
# Base API
# =========================
class BaseApi(APIView):
    """
    Base class cho các API kiểu cũ trong /api/v1/...
    """
    pass


# =========================
# Tenant mixin (FINAL)
# =========================
class TenantRequiredMixin:
    """
    Yêu cầu request phải có tenant context.
    Ưu tiên:
      1) request.tenant (object)
      2) contextvar get_current_tenant_id()
      3) request.tenant_id
    """

    def get_tenant_id(self) -> Optional[int]:
        tenant_obj = getattr(self.request, "tenant", None)
        if tenant_obj is not None and getattr(tenant_obj, "id", None) is not None:
            return int(tenant_obj.id)

        tid = get_current_tenant_id()
        if tid:
            return int(tid)

        rid = getattr(self.request, "tenant_id", None)
        if rid:
            return int(rid)

        return None

    def ensure_tenant_id(self) -> int:
        tid = self.get_tenant_id()
        if not tid:
            raise ValidationError("Missing tenant context (X-Tenant-Id).")
        return int(tid)

    def get_tenant(self):
        tenant_obj = getattr(self.request, "tenant", None)
        if tenant_obj is not None:
            return tenant_obj

        tid = self.ensure_tenant_id()
        from apps.tenants.models import Tenant

        tenant = Tenant.objects.filter(id=tid).first()
        if not tenant:
            raise ValidationError("Tenant not found.")
        return tenant