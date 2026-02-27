from __future__ import annotations

from typing import Optional, Dict, Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse

from apps.companies.models import Company
from apps.projects.models import Project, ProjectShop
from apps.projects.types import normalize_project_type, get_type_display_safe
from apps.shops.models import Shop

from apps.dashboard.projects_common import (
    mgr,
    parse_int,
    tenant_required,
    company_scope_required,
)


PROJECT_STATUS_CHOICES = {"active", "paused", "done", "inactive"}
LINK_STATUS_CHOICES = {"active", "paused", "done", "inactive"}


def _clean_str(v: Optional[str], *, max_len: int = 255) -> str:
    s = (v or "").strip()
    if len(s) > max_len:
        s = s[:max_len].strip()
    return s


def _validate_status(value: str, *, allowed: set[str], field_name: str = "status") -> str:
    v = _clean_str(value, max_len=32)
    if not v:
        return ""
    if v not in allowed:
        raise ValueError(f"Invalid {field_name}: '{v}'. Allowed: {sorted(allowed)}")
    return v


def _get_shop_or_deny(tid: int, shop_id: int, company_id: int) -> Shop:
    qs = Shop._base_manager.select_related("brand", "brand__company").filter(id=shop_id)

    field_names = {f.name for f in Shop._meta.fields}
    if "tenant" in field_names or "tenant_id" in field_names:
        qs = qs.filter(tenant_id=tid)

    shop = qs.first()
    if not shop:
        raise ValueError("Shop not found")

    brand = getattr(shop, "brand", None)
    brand_company_id = getattr(brand, "company_id", None)
    if brand_company_id is not None and int(brand_company_id) != int(company_id):
        raise ValueError("Shop out of scope (different company)")

    return shop


def _build_back_url(request) -> str:
    base = reverse("dashboard_projects:projects_dashboard")
    qs = request.META.get("QUERY_STRING") or ""
    return f"{base}?{qs}" if qs else base


@login_required
@tenant_required
@company_scope_required
def project_detail(request, project_id: int):
    tid = int(request._resolved_tenant_id)
    company_id = request._resolved_company_id
    role_label = request._resolved_role_label

    # Scope project
    qs = mgr(Project).filter(tenant_id=tid, id=int(project_id))
    if company_id is not None:
        qs = qs.filter(company_id=int(company_id))

    project = get_object_or_404(qs)
    back_url = _build_back_url(request)

    # =========================
    # POST actions (PRG)
    # =========================
    if request.method == "POST":
        action = _clean_str(request.POST.get("action"), max_len=40)

        try:
            if action == "update_project":
                name = _clean_str(request.POST.get("name"), max_len=255)
                status_in = request.POST.get("status")
                type_in = _clean_str(request.POST.get("type"), max_len=64)

                if name:
                    project.name = name

                status = _validate_status(status_in or "", allowed=PROJECT_STATUS_CHOICES, field_name="status")
                if status:
                    project.status = status

                if type_in:
                    project.type = normalize_project_type(type_in)

                project.save()
                messages.success(request, "Updated project.")

            elif action == "link_shop":
                shop_id = parse_int(request.POST.get("shop_id"))
                if not shop_id:
                    raise ValueError("Missing shop_id")

                link_status = _validate_status(
                    request.POST.get("link_status") or "active",
                    allowed=LINK_STATUS_CHOICES,
                    field_name="link_status",
                )
                link_role = _clean_str(request.POST.get("link_role"), max_len=120)

                shop = _get_shop_or_deny(tid, int(shop_id), int(project.company_id))

                defaults: Dict[str, Any] = {}
                if any(f.name == "status" for f in ProjectShop._meta.fields):
                    defaults["status"] = link_status
                if any(f.name == "role" for f in ProjectShop._meta.fields):
                    defaults["role"] = link_role

                obj, created = mgr(ProjectShop).get_or_create(
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

                messages.success(request, "Linked shop.")

            elif action == "update_link":
                ps_id = parse_int(request.POST.get("project_shop_id"))
                if not ps_id:
                    raise ValueError("Missing project_shop_id")

                link = get_object_or_404(mgr(ProjectShop), tenant_id=tid, project_id=project.id, id=int(ps_id))

                new_status = _validate_status(
                    request.POST.get("status") or "",
                    allowed=LINK_STATUS_CHOICES,
                    field_name="status",
                )
                new_role = _clean_str(request.POST.get("role"), max_len=120)

                changed = False
                if any(f.name == "status" for f in ProjectShop._meta.fields) and new_status:
                    if getattr(link, "status", None) != new_status:
                        link.status = new_status
                        changed = True

                if any(f.name == "role" for f in ProjectShop._meta.fields):
                    if getattr(link, "role", "") != new_role:
                        link.role = new_role
                        changed = True

                if changed:
                    link.save()
                    messages.success(request, "Updated link.")
                else:
                    messages.info(request, "No changes.")

            elif action == "unlink_shop":
                ps_id = parse_int(request.POST.get("project_shop_id"))
                if not ps_id:
                    raise ValueError("Missing project_shop_id")

                link = get_object_or_404(mgr(ProjectShop), tenant_id=tid, project_id=project.id, id=int(ps_id))
                link.delete()
                messages.success(request, "Unlinked shop.")

            else:
                raise ValueError(f"Unknown action: {action!r}")

        except Exception as e:
            messages.error(request, str(e))

        return redirect(request.get_full_path())

    # =========================
    # GET render
    # =========================
    links = (
        mgr(ProjectShop)
        .select_related("shop", "shop__brand")
        .filter(tenant_id=tid, project_id=project.id)
        .order_by("-id")
    )
    linked_shop_ids = list(links.values_list("shop_id", flat=True))

    shops_qs = Shop._base_manager.select_related("brand", "brand__company").all()
    field_names = {f.name for f in Shop._meta.fields}
    if "tenant" in field_names or "tenant_id" in field_names:
        shops_qs = shops_qs.filter(tenant_id=tid)

    shops_qs = shops_qs.filter(brand__company_id=project.company_id)
    if linked_shop_ids:
        shops_qs = shops_qs.exclude(id__in=linked_shop_ids)

    available_shops = list(shops_qs.order_by("-id")[:200])

    company = Company._base_manager.filter(id=project.company_id, tenant_id=tid).first()

    ctx = {
        "tenant_id": tid,
        "role_label": role_label,
        "selected_company_id": company_id,
        "back_url": back_url,
        "project": project,
        "company": company,
        "project_type_display": get_type_display_safe(project),
        "project_type_code": normalize_project_type(getattr(project, "type", None)),
        "links": links,
        "available_shops": available_shops,
    }
    return render(request, "dashboard/project_detail.html", ctx)