# apps/tenants/middleware.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.http import Http404
from django.utils.deprecation import MiddlewareMixin

from apps.tenants.models import Tenant, TenantDomain


def _clean_host(raw_host: str) -> str:
    host = (raw_host or "").strip().lower()
    if ":" in host:
        host = host.split(":", 1)[0]
    return host


def _get_header_tenant_id(request) -> Optional[int]:
    """
    Support:
    - X-Tenant-Id: 1
    - X-Tenant: 1 (alias)
    """
    raw = request.META.get("HTTP_X_TENANT_ID") or request.META.get("HTTP_X_TENANT") or ""
    raw = str(raw).strip()
    if not raw:
        return None
    try:
        return int(raw)
    except Exception:
        return None


@dataclass
class TenantContext:
    tenant: Optional[Tenant] = None
    host: str = ""


class TenantResolveMiddleware(MiddlewareMixin):
    """
    Resolve tenant theo thứ tự:
    1) Header override (DEBUG hoặc ALLOW_TENANT_HEADER=True)
    2) TenantDomain.domain == host
    3) DEV fallback cho localhost/127.0.0.1/testserver:
       - settings.DEFAULT_TENANT_ID nếu có
       - else tenant active đầu tiên
    Không resolve được -> 404 (chuẩn SaaS)
    """

    def process_request(self, request):
        if getattr(request, "_tenant_resolved", False):
            return

        host = _clean_host(request.get_host())
        tenant: Optional[Tenant] = None

        # 1) Header override
        allow_header = bool(getattr(settings, "ALLOW_TENANT_HEADER", False))
        if settings.DEBUG or allow_header:
            tid = _get_header_tenant_id(request)
            if tid:
                tenant = Tenant.objects.filter(id=tid, is_active=True).first()

        # 2) Resolve from domain table
        if tenant is None:
            td = (
                TenantDomain.objects.select_related("tenant")
                .filter(domain=host, is_active=True, tenant__is_active=True)
                .first()
            )
            if td:
                tenant = td.tenant

        # 3) DEV fallback (quan trọng: thêm "testserver")
        if tenant is None and host in {"localhost", "127.0.0.1", "testserver"}:
            default_tid = getattr(settings, "DEFAULT_TENANT_ID", None)
            if default_tid:
                tenant = Tenant.objects.filter(id=default_tid, is_active=True).first()
            if tenant is None:
                tenant = Tenant.objects.filter(is_active=True).order_by("id").first()

        if tenant is None:
            raise Http404("Tenant not found for host")

        request.tenant = tenant
        request.tenant_id = tenant.id
        request._tenant_resolved = True