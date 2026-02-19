# apps/api/v1/founder_projects_dashboard.py
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied

from apps.api.v1.base import BaseApi, api_ok, api_error
from apps.api.v1.permissions import AbilityPermission
from apps.core.policy import VIEW_API_DASHBOARD
from apps.core.permissions import is_founder
from apps.core.tenant_context import get_current_tenant_id

from apps.projects.services import ProjectDashboardService


def _get_int(v, default=None):
    try:
        return int(v)
    except Exception:
        return default


class FounderProjectsDashboardApi(BaseApi):
    """
    GET /api/v1/founder/projects/dashboard/
    - Founder/Admin only
    - xem all tenant, optional filter ?company_id=
    """
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def get(self, request):
        tid = get_current_tenant_id() or getattr(request, "tenant_id", None)
        if not tid:
            return api_error("bad_request", "Missing tenant context (X-Tenant-Id).", status=400)

        user = request.user
        if not (getattr(user, "is_superuser", False) or is_founder(user)):
            raise PermissionDenied("Founder only")

        company_id = _get_int((request.GET.get("company_id") or "").strip(), None)

        limit = request.GET.get("limit")
        limit = 50 if limit is None else max(1, min(_get_int(limit, 50), 200))

        result = ProjectDashboardService.build(tenant_id=tid, company_id=company_id, limit=limit)

        return api_ok(
            {
                "tenant_id": tid,
                "company_id": company_id,
                "summary": result.summary,
                "items": result.items,
            }
        )