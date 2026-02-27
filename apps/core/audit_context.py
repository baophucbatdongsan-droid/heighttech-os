# apps/core/audit_context.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Any, Dict

from django.http import HttpRequest

from apps.core.tenant_context import get_current_tenant


@dataclass
class AuditRequestMeta:
    tenant: Any | None
    actor: Any | None
    path: str
    method: str
    ip_address: str | None
    user_agent: str
    referer: str


def build_request_meta(request: Optional[HttpRequest]) -> AuditRequestMeta:
    tenant = None
    try:
        tenant = getattr(request, "tenant", None) or get_current_tenant()
    except Exception:
        tenant = None

    actor = getattr(request, "user", None) if request else None
    if actor is not None and not getattr(actor, "is_authenticated", False):
        actor = None

    path = (getattr(request, "path", "") or "") if request else ""
    method = (getattr(request, "method", "") or "") if request else ""

    # IP: ưu tiên X-Forwarded-For
    ip = None
    if request:
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            ip = xff.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR")

    ua = (request.META.get("HTTP_USER_AGENT", "") if request else "") or ""
    ref = (request.META.get("HTTP_REFERER", "") if request else "") or ""

    return AuditRequestMeta(
        tenant=tenant,
        actor=actor,
        path=path[:255],
        method=method[:16],
        ip_address=ip,
        user_agent=ua,
        referer=ref,
    )