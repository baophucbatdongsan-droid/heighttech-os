from __future__ import annotations

from functools import wraps
from typing import Optional, List, Callable, Iterable

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.accounts.models import Membership
from apps.companies.models import Company
from apps.core.permissions import is_founder
from apps.core.tenant_context import get_current_tenant_id


# =========================
# Generic helpers
# =========================
def mgr(Model):
    return getattr(Model, "objects_all", Model.objects)


def parse_int(v) -> Optional[int]:
    try:
        return int(str(v).strip())
    except Exception:
        return None


def clamp(n: int, lo: int, hi: int) -> int:
    try:
        n = int(n)
    except Exception:
        n = lo
    return max(lo, min(hi, n))


def keep_querystring(request: HttpRequest, drop: Optional[Iterable[str]] = None) -> str:
    params = request.GET.copy()
    if drop:
        for k in drop:
            params.pop(k, None)
    return params.urlencode()


# =========================
# Tenant + role helpers
# =========================
def current_tenant_id(request: HttpRequest) -> Optional[int]:
    return get_current_tenant_id() or getattr(request, "tenant_id", None)


def is_founder_user(user) -> bool:
    return bool(
        getattr(user, "is_authenticated", False)
        and (getattr(user, "is_superuser", False) or is_founder(user))
    )


def companies_for_user(tid: int, user) -> List[Company]:
    if is_founder_user(user):
        return list(Company._base_manager.filter(tenant_id=tid).order_by("id"))

    company_ids = list(
        Membership.objects.filter(
            user=user,
            is_active=True,
            company__tenant_id=tid,
        ).values_list("company_id", flat=True)
    )
    if not company_ids:
        return []
    return list(Company._base_manager.filter(tenant_id=tid, id__in=company_ids).order_by("id"))


def resolve_company_id_for_page(request: HttpRequest, tid: int, companies: List[Company]) -> Optional[int]:
    cid = parse_int(request.GET.get("company_id"))

    if is_founder_user(request.user):
        if cid is None:
            return None
        ok = any(int(c.id) == int(cid) for c in companies)
        return cid if ok else None

    if not companies:
        return None
    if cid is None:
        return int(companies[0].id)

    ok = any(int(c.id) == int(cid) for c in companies)
    return cid if ok else int(companies[0].id)


# =========================
# Guards (decorators)
# =========================
def tenant_required(view_fn: Callable[..., HttpResponse]):
    @wraps(view_fn)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        tid = current_tenant_id(request)
        if not tid:
            return render(
                request,
                "dashboard/projects_dashboard_page.html",
                {"error": "Missing tenant context (tenant_id)."},
                status=400,
            )
        request._resolved_tenant_id = int(tid)
        return view_fn(request, *args, **kwargs)

    return _wrapped


def company_scope_required(view_fn: Callable[..., HttpResponse]):
    @wraps(view_fn)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        tid = getattr(request, "_resolved_tenant_id", None) or current_tenant_id(request)
        if not tid:
            return render(
                request,
                "dashboard/projects_dashboard_page.html",
                {"error": "Missing tenant context (tenant_id)."},
                status=400,
            )
        tid = int(tid)

        companies = companies_for_user(tid, request.user)
        company_id = resolve_company_id_for_page(request, tid, companies)
        founder_role = is_founder_user(request.user)
        role_label = "Founder" if founder_role else "Company"

        if (not founder_role) and (company_id is None):
            return render(
                request,
                "dashboard/projects_dashboard_page.html",
                {"error": "Bạn chưa có Company active trong tenant này.", "tenant_id": tid, "role_label": role_label},
                status=403,
            )

        request._resolved_tenant_id = tid
        request._resolved_companies = companies
        request._resolved_company_id = company_id
        request._resolved_is_founder = founder_role
        request._resolved_role_label = role_label
        return view_fn(request, *args, **kwargs)

    return _wrapped