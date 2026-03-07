# apps/core/middleware_session_tenant.py
from __future__ import annotations

from django.utils.deprecation import MiddlewareMixin

SESSION_TENANT_ID = "tenant_id"


class SessionTenantContextMiddleware(MiddlewareMixin):
    """
    FINAL:
    - Tenant object đã được TenantResolveMiddleware resolve và CurrentRequestMiddleware set_current_tenant().
    - Middleware này CHỈ sync tenant_id vào session (nếu session chưa có).
    """

    def process_request(self, request):
        try:
            if request.session.get(SESSION_TENANT_ID):
                return None

            tid = getattr(request, "tenant_id", None)
            if tid:
                request.session[SESSION_TENANT_ID] = int(tid)
        except Exception:
            pass
        return None