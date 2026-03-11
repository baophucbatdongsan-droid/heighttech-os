from __future__ import annotations

from typing import Optional

from django.conf import settings
from django.http import Http404
from django.utils.deprecation import MiddlewareMixin

from apps.tenants.models import Tenant, TenantDomain

SESSION_TENANT_ID = "tenant_id"

BYPASS_PREFIXES = (
    "/admin/",
    "/login/",
    "/register/",
    "/logout/",
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

BYPASS_EXACT_PATHS = {
    "/",
}

DEV_HOSTS = {"localhost", "127.0.0.1", "testserver"}


def _clean_host(raw_host: str) -> str:
    host = (raw_host or "").strip().lower()
    if ":" in host:
        host = host.split(":", 1)[0]
    return host


def _get_header_tenant_id(request) -> Optional[int]:
    raw = request.META.get("HTTP_X_TENANT_ID") or request.META.get("HTTP_X_TENANT") or ""
    raw = str(raw).strip()
    if not raw:
        return None
    try:
        return int(raw)
    except Exception:
        return None


def _get_query_tenant_id(request) -> Optional[int]:
    raw = request.GET.get("tenant_id") or ""
    raw = str(raw).strip()
    if not raw:
        return None
    try:
        return int(raw)
    except Exception:
        return None


def _get_session_tenant_id(request) -> Optional[int]:
    try:
        tid = request.session.get(SESSION_TENANT_ID)
        if tid:
            return int(tid)
    except Exception:
        return None
    return None


def _get_default_tenant() -> Optional[Tenant]:
    default_tid = getattr(settings, "DEFAULT_TENANT_ID", None)

    if default_tid:
        tenant = Tenant.objects.filter(id=default_tid, is_active=True).first()
        if tenant:
            return tenant

    return Tenant.objects.filter(is_active=True).order_by("id").first()


class TenantResolveMiddleware(MiddlewareMixin):

    def process_request(self, request):
        if getattr(request, "_tenant_resolved", False):
            return None

        path = request.path or ""
        host = _clean_host(request.get_host())

        tenant: Optional[Tenant] = None

        allow_header = bool(getattr(settings, "ALLOW_TENANT_HEADER", False))

        # 1) header
        if settings.DEBUG or allow_header:
            tid = _get_header_tenant_id(request)
            if tid:
                tenant = Tenant.objects.filter(id=tid, is_active=True).first()

        # 2) query
        if tenant is None:
            tid = _get_query_tenant_id(request)
            if tid:
                tenant = Tenant.objects.filter(id=tid, is_active=True).first()

        # 3) session
        if tenant is None:
            tid = _get_session_tenant_id(request)
            if tid:
                tenant = Tenant.objects.filter(id=tid, is_active=True).first()

        # 4) domain
        if tenant is None:
            td = (
                TenantDomain.objects.select_related("tenant")
                .filter(domain=host, is_active=True, tenant__is_active=True)
                .first()
            )
            if td:
                tenant = td.tenant

        # 5) dev fallback
        if tenant is None and host in DEV_HOSTS:
            tenant = _get_default_tenant()

        # 6) public / hub routes thì cho đi tiếp kể cả chưa resolve tenant
        if tenant is None:
            if path in BYPASS_EXACT_PATHS or any(path.startswith(p) for p in BYPASS_PREFIXES):
                request.tenant = None
                request.tenant_id = None
                request._tenant_resolved = True
                return None

        # 7) còn lại mới 404
        if tenant is None:
            raise Http404("Tenant not found")

        request.tenant = tenant
        request.tenant_id = tenant.id
        request.session[SESSION_TENANT_ID] = tenant.id
        request._tenant_resolved = True

        return None