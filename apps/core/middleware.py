# apps/core/middleware.py
from __future__ import annotations

from dataclasses import dataclass
from threading import local
from typing import Any, Dict, Optional

from django.http import Http404
from django.utils.deprecation import MiddlewareMixin

from apps.core.tenant_context import set_current_tenant, clear_current_tenant

_thread_locals = local()


@dataclass
class RequestMeta:
    path: str = ""
    method: str = ""
    ip: str = ""
    user_agent: str = ""
    referer: str = ""


def _get_client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""


def _clean_host(raw_host: str) -> str:
    host = (raw_host or "").strip().lower()
    if ":" in host:
        host = host.split(":", 1)[0]
    return host


def set_current_request(request) -> None:
    _thread_locals.request = request
    _thread_locals.user = getattr(request, "user", None)

    _thread_locals.meta = RequestMeta(
        path=getattr(request, "path", "") or "",
        method=getattr(request, "method", "") or "",
        ip=_get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "") or "",
        referer=request.META.get("HTTP_REFERER", "") or "",
    )


def clear_current_request() -> None:
    for k in ("request", "user", "meta"):
        if hasattr(_thread_locals, k):
            delattr(_thread_locals, k)


def get_current_request():
    return getattr(_thread_locals, "request", None)


def get_current_user():
    return getattr(_thread_locals, "user", None)


def get_current_request_meta() -> Dict[str, Any]:
    meta: Optional[RequestMeta] = getattr(_thread_locals, "meta", None)
    if not meta:
        return {}
    return {
        "path": meta.path,
        "method": meta.method,
        "ip": meta.ip,
        "user_agent": meta.user_agent,
        "referer": meta.referer,
    }


def get_current_tenant_id() -> Optional[int]:
    try:
        t = getattr(get_current_request(), "tenant", None)
        if t is not None and getattr(t, "id", None):
            return int(t.id)
    except Exception:
        pass
    return None


def resolve_tenant_from_request(request):
    """
    Chuẩn SaaS:
    1) Ưu tiên header X-Tenant-ID (dev/internal)
    2) Resolve theo Host (subdomain/custom domain) qua TenantDomain.domain
    3) DEV fallback: localhost/127.0.0.1 -> DEFAULT_TENANT_ID hoặc Tenant.first()
    4) Không resolve được -> 404
    """
    from django.conf import settings
    from apps.tenants.models import Tenant, TenantDomain

    # 1) Header override
    tenant_id = (
        request.headers.get("X-Tenant-ID")
        or request.headers.get("X-Tenant-Id")
        or request.META.get("HTTP_X_TENANT_ID")
    )
    if tenant_id:
        try:
            return Tenant.objects.get(id=int(tenant_id), is_active=True)
        except Exception:
            pass

    # 2) Resolve by Host
    host = _clean_host(request.get_host())

    td = (
        TenantDomain.objects.select_related("tenant")
        .filter(domain=host, is_active=True, tenant__is_active=True)
        .first()
    )
    if td:
        return td.tenant

    # 3) DEV fallback
    if host in {"localhost", "127.0.0.1"}:
        default_id = getattr(settings, "DEFAULT_TENANT_ID", None)
        if default_id:
            t = Tenant.objects.filter(id=default_id, is_active=True).first()
            if t:
                return t
        return Tenant.objects.filter(is_active=True).first()

    raise Http404("Tenant not found for host")


class CurrentRequestMiddleware(MiddlewareMixin):
    def process_request(self, request):
        set_current_request(request)

        tenant = resolve_tenant_from_request(request)
        request.tenant = tenant
        request.tenant_id = getattr(tenant, "id", None)

        set_current_tenant(tenant)

    def process_response(self, request, response):
        clear_current_tenant()
        clear_current_request()
        return response

    def process_exception(self, request, exception):
        clear_current_tenant()
        clear_current_request()
        return None