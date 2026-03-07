from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Optional, Set

from django.core.paginator import Paginator
from django.db.models import Count
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response  # ✅ add

from apps.accounts.models import Membership
from apps.api.v1.base import BaseApi
from apps.api.v1.permissions import AbilityPermission
from apps.core.permissions import is_founder
from apps.core.policy import VIEW_API_DASHBOARD
from apps.core.tenant_context import get_current_tenant_id
from apps.projects.models import Project, ProjectShop
from apps.projects.types import normalize_project_type


def _mgr(Model):
    return getattr(Model, "objects_all", Model.objects)


def _get_int(v, default=None):
    try:
        return int(v)
    except Exception:
        return default


def _get_page_params(request, default_size: int = 50, max_size: int = 200):
    page = _get_int(request.GET.get("page"), 1) or 1
    page_size = _get_int(request.GET.get("page_size"), default_size) or default_size
    page = max(1, page)
    page_size = max(1, min(page_size, max_size))
    return page, page_size


def _current_tenant_id(request) -> Optional[int]:
    return get_current_tenant_id() or getattr(request, "tenant_id", None)


def _ensure_tenant_or_400(request) -> int:
    tid = _current_tenant_id(request)
    if not tid:
        raise ValidationError("Missing tenant context (X-Tenant-Id).")
    return int(tid)


def _get_header(request, key: str) -> Optional[str]:
    try:
        v = request.headers.get(key)
        if v:
            return v
    except Exception:
        pass
    meta_key = "HTTP_" + key.upper().replace("-", "_")
    return request.META.get(meta_key)


def _is_founder_user(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    return bool(getattr(user, "is_superuser", False) or is_founder(user))


def _resolve_company_scope(request, tenant_id: int) -> Optional[int]:
    user = request.user

    # founder/admin: company_id optional via ?company_id=
    if _is_founder_user(user):
        q = (request.GET.get("company_id") or "").strip()
        return _get_int(q, None)

    # non-founder: required X-Company-Id
    raw = (_get_header(request, "X-Company-Id") or "").strip()
    company_id = _get_int(raw, None)
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


def _get_type_display_safe(p: Project) -> str:
    try:
        if hasattr(p, "get_type_display"):
            return p.get_type_display()
    except Exception:
        pass
    return str(getattr(p, "type", ""))


def serialize_project(p: Project) -> Dict[str, Any]:
    type_display = _get_type_display_safe(p)
    type_code = normalize_project_type(getattr(p, "type", None))
    return {
        "id": p.id,
        "tenant_id": p.tenant_id,
        "company_id": p.company_id,
        "name": p.name,
        "type": type_display,
        "type_code": type_code,
        "status": p.status,
        "created_at": getattr(p, "created_at", None),
        "updated_at": getattr(p, "updated_at", None),
    }


class ProjectsDashboardApi(BaseApi):
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def get(self, request):
        tid = _ensure_tenant_or_400(request)
        company_id = _resolve_company_scope(request, tenant_id=tid)

        qs = _mgr(Project).filter(tenant_id=tid).order_by("-id")
        if company_id is not None:
            qs = qs.filter(company_id=company_id)

        # optional filters
        status = (request.GET.get("status") or "").strip()
        if status:
            qs = qs.filter(status=status)

        t_raw = (request.GET.get("type") or "").strip()
        if t_raw:
            t_norm = normalize_project_type(t_raw)
            candidates: Set[str] = {t_norm, t_raw, t_raw.lower(), t_raw.upper()}
            qs = qs.filter(type__in=list(candidates))

        # paginate items (dashboard vẫn trả items để test/FE dùng)
        page, page_size = _get_page_params(request, default_size=50, max_size=200)
        paginator = Paginator(qs, page_size)
        page_obj = paginator.get_page(page)

        items = [serialize_project(p) for p in page_obj.object_list]

        # summary full qs
        total_projects = paginator.count

        by_status: Dict[str, int] = {}
        for row in qs.values("status").annotate(c=Count("id")):
            st = (row.get("status") or "").strip()
            by_status[st] = int(row.get("c") or 0)

        by_type_counter: Counter[str] = Counter()
        for row in qs.values("type").annotate(c=Count("id")):
            raw_t = (row.get("type") or "").strip()
            code = normalize_project_type(raw_t)
            by_type_counter[code] += int(row.get("c") or 0)
        by_type = dict(by_type_counter)

        links = _mgr(ProjectShop).filter(tenant_id=tid).filter(project__tenant_id=tid)
        if company_id is not None:
            links = links.filter(project__company_id=company_id)

        shops_total = links.count()
        shops_by_status: Dict[str, int] = {}
        for row in links.values("status").annotate(c=Count("id")):
            st = (row.get("status") or "").strip()
            shops_by_status[st] = int(row.get("c") or 0)

        data = {
            "tenant_id": tid,
            "company_id": company_id,
            "summary": {
                "total_projects": total_projects,
                "by_status": by_status,
                "by_type": by_type,
                "shops": {
                    "total": shops_total,
                    "by_status": shops_by_status,
                },
            },
            "items": items,
        }

        meta = {
            "page": page_obj.number,
            "page_size": page_size,
            "total_items": paginator.count,
            "total_pages": paginator.num_pages,
            "has_next": page_obj.has_next(),
            "has_prev": page_obj.has_previous(),
        }

        # ✅ HARD-GUARANTEE contract for tests: always have "data"
        return Response({"ok": True, "data": data, "meta": meta})