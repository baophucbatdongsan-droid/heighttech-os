from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

from apps.accounts.models import Membership


_CURRENT_TENANT_ID: ContextVar[Optional[int]] = ContextVar("CURRENT_TENANT_ID", default=None)


def set_current_tenant(tenant_id: Optional[int]) -> None:
    try:
        _CURRENT_TENANT_ID.set(int(tenant_id) if tenant_id else None)
    except Exception:
        _CURRENT_TENANT_ID.set(None)


def set_current_tenant_id(tenant_id: Optional[int]) -> None:
    set_current_tenant(tenant_id)


def get_current_tenant() -> Optional[int]:
    try:
        tid = _CURRENT_TENANT_ID.get()
        return int(tid) if tid else None
    except Exception:
        return None


def get_current_tenant_id() -> Optional[int]:
    return get_current_tenant()


def clear_current_tenant() -> None:
    _CURRENT_TENANT_ID.set(None)


def clear_current_tenant_id() -> None:
    clear_current_tenant()


def get_request_tenant_id(request) -> Optional[int]:
    """
    Resolve tenant_id theo thứ tự an toàn nhất:

    1) membership active của user hiện tại
    2) actor_ctx.tenant_id
    3) request.tenant_id
    4) request.tenant.id
    5) X-Tenant-Id header
    6) contextvar hiện tại
    """
    try:
        user = getattr(request, "user", None)
        if user and getattr(user, "is_authenticated", False):
            m = (
                Membership.objects.filter(user=user, is_active=True)
                .select_related("tenant", "company")
                .order_by("id")
                .first()
            )
            if m and getattr(m, "tenant_id", None):
                return int(m.tenant_id)
    except Exception:
        pass

    try:
        actor_ctx = getattr(request, "actor_ctx", None)
        tid = getattr(actor_ctx, "tenant_id", None)
        if tid is not None:
            return int(tid)
    except Exception:
        pass

    try:
        tid = getattr(request, "tenant_id", None)
        if tid is not None:
            return int(tid)
    except Exception:
        pass

    try:
        tenant = getattr(request, "tenant", None)
        tid = getattr(tenant, "id", None)
        if tid is not None:
            return int(tid)
    except Exception:
        pass

    try:
        raw = request.headers.get("X-Tenant-Id")
        if raw:
            return int(raw)
    except Exception:
        pass

    return get_current_tenant()


def require_request_tenant_id(request) -> int:
    tid = get_request_tenant_id(request)
    if not tid:
        raise RuntimeError("Tenant context missing")
    return int(tid)