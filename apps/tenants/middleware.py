# apps/tenants/middleware.py
from __future__ import annotations
from apps.tenants.models import Tenant

class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = Tenant.objects.first()
        return self.get_response(request)
    


from dataclasses import dataclass
from typing import Optional

from django.http import Http404
from django.utils.deprecation import MiddlewareMixin

from apps.tenants.models import TenantDomain, Tenant


def _clean_host(raw_host: str) -> str:
    # raw_host có thể là "abc.com:8000"
    host = (raw_host or "").strip().lower()
    if ":" in host:
        host = host.split(":", 1)[0]
    return host


@dataclass
class TenantContext:
    tenant: Optional[Tenant] = None
    host: str = ""


class TenantResolveMiddleware(MiddlewareMixin):
    """
    Resolve tenant từ request.get_host():
    - Tìm TenantDomain.host == host
    - Nếu không có:
        - DEV: localhost/127.0.0.1 => tenant mặc định (optional)
        - hoặc raise 404
    - Optional API override: header X-Tenant (tenant_id) (chỉ khi bật setting)
    """

    def process_request(self, request):
        host = _clean_host(request.get_host())

        # optional: allow override by header for API/testing
        allow_header = getattr(request, "ALLOW_TENANT_HEADER", None)  # not used
        if getattr(request, "_tenant_resolved", False):
            return

        tenant = None

        # 1) Resolve from domain table
        td = (
            TenantDomain.objects.select_related("tenant")
            .filter(host=host, is_active=True, tenant__is_active=True)
            .first()
        )
        if td:
            tenant = td.tenant

        # 2) DEV fallback for localhost
        if tenant is None and host in {"localhost", "127.0.0.1"}:
            default_id = getattr(request, "DEFAULT_TENANT_ID", None)  # not used
            default_tenant_id = getattr(__import__("django.conf").conf.settings, "DEFAULT_TENANT_ID", None)
            if default_tenant_id:
                tenant = Tenant.objects.filter(id=default_tenant_id, is_active=True).first()

        if tenant is None:
            # không resolve được tenant => 404 (đúng chuẩn SaaS)
            raise Http404("Tenant not found for host")

        request.tenant = tenant
        request.tenant_id = tenant.id
        request._tenant_resolved = True