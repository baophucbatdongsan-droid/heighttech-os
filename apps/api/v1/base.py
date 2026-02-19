# apps/api/v1/base.py
from __future__ import annotations

from typing import Any, Dict, Optional

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import NotFound

def api_ok(data: Any = None, meta: Optional[Dict[str, Any]] = None, status: int = 200):
    return Response(
        {"ok": True, "data": data, "meta": meta or {}, "error": None},
        status=status,
    )


def api_error(code: str, message: str, status: int = 400, meta: Optional[Dict[str, Any]] = None):
    return Response(
        {"ok": False, "data": None, "meta": meta or {}, "error": {"code": code, "message": message}},
        status=status,
    )


class BaseApi(APIView):
    """Base class cho mọi API v1."""
    pass




class TenantRequiredMixin:
    """
    Đảm bảo request có tenant (middleware đã set request.tenant).
    Dùng cho mọi API cần tenant.
    """

    def get_tenant(self):
        t = getattr(self.request, "tenant", None)
        if t is None:
            raise NotFound("Tenant not resolved")
        return t