from __future__ import annotations

from typing import Any, Dict, Optional, Set

from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated

from apps.api.v1.base import BaseApi, api_error, api_ok
from apps.api.v1.permissions import AbilityPermission
from apps.core.permissions import is_founder
from apps.core.policy import VIEW_API_DASHBOARD
from apps.core.tenant_context import get_current_tenant_id

from apps.accounts.models import Membership
from apps.companies.models import Company
from apps.projects.models import Project, ProjectShop
from apps.shops.models import Shop

from apps.projects.types import normalize_project_type


# -------------------------
# Helpers
# -------------------------
def _mgr(Model):
    return getattr(Model, "objects_all", Model.objects)


def _get_page_params(request, default_size: int = 50, max_size: int = 200):
    try:
        page = int(request.GET.get("page", "1"))
    except Exception:
        page = 1

    try:
        page_size = int(request.GET.get("page_size", str(default_size)))
    except Exception:
        page_size = default_size

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


def _is_founder_user(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    return bool(getattr(user, "is_superuser", False) or is_founder(user))


def _get_header(request, key: str) -> Optional[str]:
    try:
        v = request.headers.get(key)
        if v:
            return v
    except Exception:
        pass
    meta_key = "HTTP_" + key.upper().replace("-", "_")
    return request.META.get(meta_key)


def _resolve_company_scope(request, tenant_id: int) -> Optional[int]:
    """
    - Founder/superuser: company_id optional (filter bằng query param ?company_id=)
    - Non-founder: bắt buộc X-Company-Id và phải có membership active ở company đó
    """
    user = request.user

    if _is_founder_user(user):
        q = (request.GET.get("company_id") or "").strip()
        if not q:
            return None
        try:
            return int(q)
        except Exception:
            raise PermissionDenied("Invalid company_id query param.")

    raw = (_get_header(request, "X-Company-Id") or "").strip()
    if not raw:
        raise PermissionDenied("Missing X-Company-Id. Bạn cần chọn Company.")
    try:
        company_id = int(raw)
    except Exception:
        raise PermissionDenied("Invalid X-Company-Id.")

    ok = Membership.objects.filter(
        user=user,
        company_id=company_id,
        is_active=True,
        company__tenant_id=tenant_id,
    ).exists()
    if not ok:
        raise PermissionDenied("Forbidden: company scope not allowed.")

    return company_id


def _get_company_or_deny(tid: int, company_id: int) -> Company:
    c = Company._base_manager.filter(id=company_id, tenant_id=tid).first()
    if not c:
        raise PermissionDenied("Company matching query does not exist.")
    return c


def _get_project_or_404(tid: int, project_id: int, company_id: Optional[int]) -> Project:
    qs = _mgr(Project).filter(id=project_id, tenant_id=tid)
    if company_id is not None:
        qs = qs.filter(company_id=company_id)
    return get_object_or_404(qs)


def _get_shop_or_deny(tid: int, shop_id: int, company_id: Optional[int]) -> Shop:
    qs = Shop._base_manager.select_related("brand", "brand__company").filter(id=shop_id)

    field_names = {f.name for f in Shop._meta.fields}
    if "tenant" in field_names or "tenant_id" in field_names:
        qs = qs.filter(tenant_id=tid)

    shop = qs.first()
    if not shop:
        raise PermissionDenied("Shop matching query does not exist.")

    if company_id is not None:
        brand = getattr(shop, "brand", None)
        brand_company_id = getattr(brand, "company_id", None)
        if brand_company_id is not None and int(brand_company_id) != int(company_id):
            raise PermissionDenied("Shop matching query does not exist (out of scope).")

    return shop


def _get_type_display_safe(p: Project) -> str:
    try:
        if hasattr(p, "get_type_display"):
            return p.get_type_display()
    except Exception:
        pass
    return str(getattr(p, "type", ""))


def serialize_project(p: Project) -> Dict[str, Any]:
    type_display = _get_type_display_safe(p)  # vd: "BUILD_CHANNEL"
    type_code = normalize_project_type(getattr(p, "type", None))  # vd: "build_channel"
    return {
        "id": p.id,
        "tenant_id": p.tenant_id,
        "company_id": p.company_id,
        "name": p.name,
        "type": type_display,      # display (UPPER) cho FE
        "type_code": type_code,    # canonical (lower) cho filter/summary
        "status": p.status,
        "created_at": getattr(p, "created_at", None),
        "updated_at": getattr(p, "updated_at", None),
    }


def serialize_project_shop(ps: ProjectShop) -> Dict[str, Any]:
    return {
        "id": ps.id,
        "tenant_id": getattr(ps, "tenant_id", None),
        "project_id": getattr(ps, "project_id", None),
        "shop_id": getattr(ps, "shop_id", None),
        "status": getattr(ps, "status", None),
        "role": getattr(ps, "role", None),
        "created_at": getattr(ps, "created_at", None),
        "updated_at": getattr(ps, "updated_at", None),
    }


# -------------------------
# APIs
# -------------------------
class ProjectListCreateApi(BaseApi):
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def get(self, request):
        tid = _ensure_tenant_or_400(request)
        scoped_company_id = _resolve_company_scope(request, tenant_id=tid)

        qs = _mgr(Project).filter(tenant_id=tid).order_by("-id")

        if scoped_company_id is not None:
            qs = qs.filter(company_id=scoped_company_id)

        status = (request.GET.get("status") or "").strip()
        if status:
            qs = qs.filter(status=status)

        t_raw = (request.GET.get("type") or "").strip()
        if t_raw:
            t_norm = normalize_project_type(t_raw)
            candidates: Set[str] = {t_norm, t_raw, t_raw.lower(), t_raw.upper()}
            qs = qs.filter(type__in=list(candidates))

        page, page_size = _get_page_params(request)
        paginator = Paginator(qs, page_size)
        page_obj = paginator.get_page(page)

        data = {"items": [serialize_project(p) for p in page_obj.object_list]}
        meta = {
            "page": page_obj.number,
            "page_size": page_size,
            "total_items": paginator.count,
            "total_pages": paginator.num_pages,
            "has_next": page_obj.has_next(),
            "has_prev": page_obj.has_previous(),
        }
        # ✅ FINAL: data.items nằm đúng tại res.json()["data"]["items"]
        return api_ok(data, meta=meta)

    def post(self, request):
        tid = _ensure_tenant_or_400(request)
        scoped_company_id = _resolve_company_scope(request, tenant_id=tid)

        name = (request.data.get("name") or "").strip()
        if not name:
            return api_error("bad_request", "Thiếu name", status=400)

        status = (request.data.get("status") or "active").strip()
        ptype = normalize_project_type(request.data.get("type") or "SHOP_OPERATION")

        body_company_id = request.data.get("company_id")

        if scoped_company_id is not None:
            if body_company_id and str(body_company_id).strip() and int(body_company_id) != int(scoped_company_id):
                raise PermissionDenied("Forbidden: cannot create project for another company")
            company_id = int(scoped_company_id)
        else:
            if not body_company_id:
                return api_error("bad_request", "Thiếu company_id", status=400)
            try:
                company_id = int(body_company_id)
            except Exception:
                return api_error("bad_request", "company_id không hợp lệ", status=400)

        company = _get_company_or_deny(tid, company_id)

        p = _mgr(Project).create(
            tenant_id=tid,
            company_id=company.id,
            name=name,
            type=ptype,  # canonical lowercase
            status=status,
        )

        # ✅ FINAL: data.item nằm đúng tại res.json()["data"]["item"]
        return api_ok({"item": serialize_project(p)})


class ProjectDetailApi(BaseApi):
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def get(self, request, project_id: int):
        tid = _ensure_tenant_or_400(request)
        scoped_company_id = _resolve_company_scope(request, tenant_id=tid)
        p = _get_project_or_404(tid, int(project_id), scoped_company_id)
        return api_ok({"item": serialize_project(p)})

    def patch(self, request, project_id: int):
        tid = _ensure_tenant_or_400(request)
        scoped_company_id = _resolve_company_scope(request, tenant_id=tid)
        p = _get_project_or_404(tid, int(project_id), scoped_company_id)

        if "name" in request.data:
            p.name = (request.data.get("name") or "").strip() or p.name
        if "status" in request.data:
            p.status = (request.data.get("status") or "").strip() or p.status
        if "type" in request.data:
            p.type = normalize_project_type(request.data.get("type"))

        if "company_id" in request.data:
            if scoped_company_id is not None:
                raise PermissionDenied("Forbidden: cannot change company_id")
            raw = request.data.get("company_id")
            try:
                new_company_id = int(raw)
            except Exception:
                return api_error("bad_request", "company_id không hợp lệ", status=400)
            company = _get_company_or_deny(tid, new_company_id)
            p.company_id = company.id

        p.save()
        return api_ok({"item": serialize_project(p)})

    def delete(self, request, project_id: int):
        tid = _ensure_tenant_or_400(request)
        scoped_company_id = _resolve_company_scope(request, tenant_id=tid)
        p = _get_project_or_404(tid, int(project_id), scoped_company_id)
        p.delete()
        return api_ok({"deleted": True})


class ProjectShopListCreateApi(BaseApi):
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def get(self, request, project_id: int):
        tid = _ensure_tenant_or_400(request)
        scoped_company_id = _resolve_company_scope(request, tenant_id=tid)

        project = _get_project_or_404(tid, int(project_id), scoped_company_id)
        qs = _mgr(ProjectShop).filter(tenant_id=tid, project_id=project.id).order_by("-id")

        status = (request.GET.get("status") or "").strip()
        if status and any(f.name == "status" for f in ProjectShop._meta.fields):
            qs = qs.filter(status=status)

        page, page_size = _get_page_params(request)
        paginator = Paginator(qs, page_size)
        page_obj = paginator.get_page(page)

        data = {"items": [serialize_project_shop(x) for x in page_obj.object_list]}
        meta = {
            "page": page_obj.number,
            "page_size": page_size,
            "total_items": paginator.count,
            "total_pages": paginator.num_pages,
            "has_next": page_obj.has_next(),
            "has_prev": page_obj.has_previous(),
        }
        return api_ok(data, meta=meta)

    def post(self, request, project_id: int):
        tid = _ensure_tenant_or_400(request)
        scoped_company_id = _resolve_company_scope(request, tenant_id=tid)

        project = _get_project_or_404(tid, int(project_id), scoped_company_id)

        shop_id = request.data.get("shop_id")
        if not shop_id:
            return api_error("bad_request", "Thiếu shop_id", status=400)
        try:
            shop_id = int(shop_id)
        except Exception:
            return api_error("bad_request", "shop_id không hợp lệ", status=400)

        shop = _get_shop_or_deny(tid, shop_id, project.company_id)

        defaults: Dict[str, Any] = {}
        if any(f.name == "status" for f in ProjectShop._meta.fields):
            defaults["status"] = (request.data.get("status") or "active").strip()
        if any(f.name == "role" for f in ProjectShop._meta.fields) and request.data.get("role"):
            defaults["role"] = (request.data.get("role") or "").strip()

        obj, created = _mgr(ProjectShop).get_or_create(
            tenant_id=tid,
            project_id=project.id,
            shop_id=shop.id,
            defaults=defaults,
        )

        if not created:
            changed = False
            if "status" in defaults and getattr(obj, "status", None) != defaults["status"]:
                obj.status = defaults["status"]
                changed = True
            if "role" in defaults and getattr(obj, "role", None) != defaults["role"]:
                obj.role = defaults["role"]
                changed = True
            if changed:
                obj.save()

        return api_ok({"item": serialize_project_shop(obj)})


class ProjectShopDetailApi(BaseApi):
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def _get_obj(
        self,
        tid: int,
        project_id: int,
        project_shop_id: int,
        scoped_company_id: Optional[int],
    ) -> ProjectShop:
        _get_project_or_404(tid, project_id, scoped_company_id)
        return get_object_or_404(_mgr(ProjectShop), id=project_shop_id, tenant_id=tid, project_id=project_id)

    def patch(self, request, project_id: int, project_shop_id: int):
        tid = _ensure_tenant_or_400(request)
        scoped_company_id = _resolve_company_scope(request, tenant_id=tid)
        obj = self._get_obj(tid, int(project_id), int(project_shop_id), scoped_company_id)

        changed = False
        if any(f.name == "status" for f in ProjectShop._meta.fields) and "status" in request.data:
            obj.status = (request.data.get("status") or "").strip() or obj.status
            changed = True
        if any(f.name == "role" for f in ProjectShop._meta.fields) and "role" in request.data:
            obj.role = (request.data.get("role") or "").strip() or obj.role
            changed = True

        if changed:
            obj.save()

        return api_ok({"item": serialize_project_shop(obj)})

    def delete(self, request, project_id: int, project_shop_id: int):
        tid = _ensure_tenant_or_400(request)
        scoped_company_id = _resolve_company_scope(request, tenant_id=tid)
        obj = self._get_obj(tid, int(project_id), int(project_shop_id), scoped_company_id)
        obj.delete()
        return api_ok({"deleted": True})