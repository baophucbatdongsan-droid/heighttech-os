# apps/api/v1/projects_dashboard.py
from __future__ import annotations

from typing import Optional, Dict

from django.db.models import Count
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated

from apps.api.v1.base import BaseApi, api_error, api_ok
from apps.api.v1.permissions import AbilityPermission
from apps.core.permissions import is_founder
from apps.core.policy import VIEW_API_DASHBOARD
from apps.core.tenant_context import get_current_tenant_id

from apps.accounts.models import Membership
from apps.projects.models import Project, ProjectShop

# ✅ ưu tiên import normalize từ module types (nếu bạn đã tách),
#    fallback về services để không bị gãy nếu chưa tách.
try:
    from apps.projects.types import normalize_project_type
except Exception:
    from apps.projects.services import normalize_project_type


def _get_int(v, default=None):
    try:
        return int(v)
    except Exception:
        return default


def _resolve_company_scope(request, tenant_id: int) -> Optional[int]:
    """
    - Founder/superuser: company_id optional qua query param ?company_id=
    - Non-founder: bắt buộc X-Company-Id + membership active
    """
    user = request.user
    if getattr(user, "is_superuser", False) or is_founder(user):
        q_company = request.GET.get("company_id")
        return _get_int(q_company, None)

    header_company = request.headers.get("X-Company-Id") or request.META.get("HTTP_X_COMPANY_ID")
    company_id = _get_int(header_company, None)
    if company_id is None:
        raise PermissionDenied("Missing X-Company-Id. Bạn cần chọn Company.")

    ok = Membership.objects.filter(
        user=user,
        company_id=company_id,
        is_active=True,
        company__tenant_id=tenant_id,
    ).exists()
    if not ok:
        raise PermissionDenied("Forbidden: company scope not allowed.")
    return company_id


class ProjectsDashboardApi(BaseApi):
    """
    GET /api/v1/projects/dashboard/
    - company scoped cho non-founder
    - founder có thể xem all hoặc filter ?company_id=
    """
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def get(self, request):
        tid = get_current_tenant_id() or getattr(request, "tenant_id", None)
        if not tid:
            return api_error("bad_request", "Missing tenant context (X-Tenant-Id).", status=400)

        tid = int(tid)  # ✅ FIX: cast 1 lần cho chắc

        try:
            company_id = _resolve_company_scope(request, tenant_id=tid)
        except PermissionDenied as e:
            return api_error("forbidden", str(e), status=403)

        qs = Project.objects_all.filter(tenant_id=tid)
        if company_id is not None:
            qs = qs.filter(company_id=company_id)

        # -------------------------
        # Projects summary (DB aggregate)
        # -------------------------
        total_projects = qs.count()

        by_status: Dict[str, int] = {}
        for row in qs.values("status").annotate(c=Count("id")):
            st = row["status"] or ""
            by_status[st] = int(row["c"] or 0)

        # ✅ FIX: normalize -> tránh split key SHOP_OPERATION vs shop_operation
        by_type: Dict[str, int] = {}
        for row in qs.values("type").annotate(c=Count("id")):
            t_raw = row["type"] or ""
            t_code = normalize_project_type(t_raw)
            by_type[t_code] = by_type.get(t_code, 0) + int(row["c"] or 0)

        # -------------------------
        # Shops summary (DB aggregate)
        #   - luôn trả đủ key để FE ổn định
        #   - không cho "mọc key lạ"
        # -------------------------
        links = ProjectShop.objects_all.filter(tenant_id=tid, project__tenant_id=tid)
        if company_id is not None:
            links = links.filter(project__company_id=company_id)

        shops_total = links.count()

        shops_status: Dict[str, int] = {"active": 0, "paused": 0, "done": 0, "inactive": 0}
        for row in links.values("status").annotate(c=Count("id")):
            st = (row["status"] or "").strip()
            if st in shops_status:  # ✅ FIX: giữ response ổn định, không mọc key khác
                shops_status[st] = int(row["c"] or 0)

        data = {
            "tenant_id": tid,
            "company_id": company_id,
            "summary": {
                "total_projects": total_projects,
                "by_status": by_status,
                "by_type": by_type,  # canonical type_code
                "shops": {
                    "total": shops_total,
                    **shops_status,
                },
            },
        }
        return api_ok(data)