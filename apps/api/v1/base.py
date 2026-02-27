# apps/api/v1/base.py
from __future__ import annotations

from typing import Any, Dict, Optional

from rest_framework.response import Response
from rest_framework.views import APIView


# =========================
# Response helpers (COMPAT)
# =========================
def api_ok(data: Any = None, meta: Optional[Dict[str, Any]] = None, status: int = 200) -> Response:
    payload: Dict[str, Any] = {"ok": True}
    if data is not None:
        # nếu data đã là dict {"items": ...} thì gộp vào
        if isinstance(data, dict):
            payload.update(data)
        else:
            payload["data"] = data
    if meta is not None:
        payload["meta"] = meta
    return Response(payload, status=status)


def api_error(code: str, message: str, status: int = 400, extra: Optional[Dict[str, Any]] = None) -> Response:
    payload: Dict[str, Any] = {"ok": False, "code": code, "message": message}
    if extra:
        payload.update(extra)
    return Response(payload, status=status)


# =========================
# Base API
# =========================
class BaseApi(APIView):
    """
    Base class cho các API kiểu cũ trong /api/v1/...
    (giữ để không phải rewrite hết project)
    """
    pass


# =========================
# Tenant mixin
# =========================
class TenantRequiredMixin:
    """
    Yêu cầu request phải có tenant_id (thường được set bởi middleware)
    và cung cấp helper get_tenant().
    """
    def get_tenant(self):
        tenant = getattr(self.request, "tenant", None)
        if tenant is not None:
            return tenant

        tenant_id = getattr(self.request, "tenant_id", None)
        if tenant_id:
            # bạn đang có Tenant model ở đâu thì import đúng chỗ này
            from apps.tenants.models import Tenant  # chỉnh path nếu khác
            return Tenant.objects.get(id=int(tenant_id))

        raise ValueError("tenant not found on request (missing request.tenant or request.tenant_id)")