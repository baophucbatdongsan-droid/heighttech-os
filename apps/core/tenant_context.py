# apps/core/tenant_context.py
from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

_current_tenant = ContextVar("current_tenant", default=None)

def set_current_tenant(tenant) -> None:
    _current_tenant.set(tenant)

def clear_current_tenant() -> None:
    _current_tenant.set(None)

def get_current_tenant():
    return _current_tenant.get()

def get_current_tenant_id() -> Optional[int]:
    t = get_current_tenant()
    if t is None:
        return None
    tid = getattr(t, "id", None)
    return int(tid) if tid else None