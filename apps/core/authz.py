# apps/core/authz.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from django.contrib.auth.models import AnonymousUser


@dataclass(frozen=True)
class ActorContext:
    tenant_id: Optional[int]
    role: str  # "founder" | "admin" | "operator" | "client" | ...


def safe_getattr(obj, name: str, default=None):
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


def get_actor_ctx(request) -> ActorContext:
    user = getattr(request, "user", None)
    if not user or isinstance(user, AnonymousUser) or not getattr(user, "is_authenticated", False):
        return ActorContext(tenant_id=None, role="anonymous")

    # Tenant: ưu tiên tenant_context nếu bạn đã có middleware set_current_tenant
    tenant_id = safe_getattr(request, "tenant_id", None)
    if tenant_id is None:
        tenant = safe_getattr(request, "tenant", None)
        tenant_id = safe_getattr(tenant, "id", None)

    # Role: ưu tiên request.role nếu bạn set từ middleware; fallback user flags
    role = safe_getattr(request, "role", None)
    if not role:
        if safe_getattr(user, "is_superuser", False):
            role = "founder"
        elif safe_getattr(user, "is_staff", False):
            role = "admin"
        else:
            role = "operator"

    return ActorContext(tenant_id=tenant_id, role=str(role))


def has_any_role(role: str, allow: Iterable[str]) -> bool:
    r = (role or "").strip().lower()
    allow_set = {a.strip().lower() for a in allow}
    return r in allow_set