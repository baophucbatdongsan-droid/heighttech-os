from __future__ import annotations

from django.core.cache import cache
from django.http import Http404


PUBLIC_PATH_PREFIXES = (
    "/login/",
    "/register/",
    "/logout/",
    "/admin/",
    "/static/",
    "/media/",
    "/metrics/",
    "/favicon.ico",
    "/robots.txt",
    "/os/",
    "/app/",
    "/work/",
    "/api/",
)

TENANT_CACHE_TTL = 300  # 5 phút


def _clean_host(raw_host: str) -> str:
    host = (raw_host or "").strip().lower()
    if ":" in host:
        host = host.split(":", 1)[0]
    return host


def resolve_tenant_cached(request):
    from django.conf import settings
    from apps.tenants.models import Tenant, TenantDomain

    path = request.path or ""

    # Public / hub routes: không ép resolve tenant theo host
    if any(path.startswith(p) for p in PUBLIC_PATH_PREFIXES):
        return None

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

    host = _clean_host(request.get_host())
    cache_key = f"tenant:host:{host}"

    tenant = cache.get(cache_key)
    if tenant:
        return tenant

    td = (
        TenantDomain.objects.select_related("tenant")
        .filter(domain=host, is_active=True, tenant__is_active=True)
        .first()
    )
    if td:
        cache.set(cache_key, td.tenant, TENANT_CACHE_TTL)
        return td.tenant

    if host in {"localhost", "127.0.0.1", "testserver"}:
        default_id = getattr(settings, "DEFAULT_TENANT_ID", None)
        if default_id:
            t = Tenant.objects.filter(id=default_id, is_active=True).first()
            if t:
                return t
        t = Tenant.objects.filter(is_active=True).first()
        if t:
            return t

    raise Http404("Tenant not found for host")