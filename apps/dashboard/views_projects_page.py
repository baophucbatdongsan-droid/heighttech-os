# apps/dashboard/views_projects_page.py
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.dashboard.projects_common import (
    companies_for_user,
    current_tenant_id,
    is_founder_user,
    keep_querystring,
    resolve_company_id_for_page,
)
from apps.dashboard.projects_queries import ProjectsDashboardQuery
from apps.dashboard.projects_services import ProjectsDashboardService


TEMPLATE_PAGE = "dashboard/projects/page.html"


@login_required
def projects_dashboard_page(request):
    """
    Trang Dashboard Dự án (Level 9)
    - Filter + sort + paginate
    - Preview count (AJAX) để confirm trước khi bulk update toàn bộ theo bộ lọc
    """
    tid = current_tenant_id(request)
    if not tid:
        return render(
            request,
            TEMPLATE_PAGE,
            {"error": "Thiếu ngữ cảnh tenant (tenant_id)."},
            status=400,
        )
    tid = int(tid)

    companies = companies_for_user(tid, request.user)
    company_id = resolve_company_id_for_page(request, tid, companies)

    founder_role = is_founder_user(request.user)
    role_label = "Founder" if founder_role else "Company"

    # Non-founder bắt buộc có company scope
    if (not founder_role) and (company_id is None):
        return render(
            request,
            TEMPLATE_PAGE,
            {"error": "Bạn chưa có Company đang hoạt động trong tenant này."},
            status=403,
        )

    query = ProjectsDashboardQuery.from_request(request)

    # ✅ AJAX preview count: cho nút "Áp dụng TẤT CẢ theo bộ lọc"
    if request.GET.get("preview_count") == "1" and request.headers.get("X-Requested-With") == "XMLHttpRequest":
        qs = ProjectsDashboardService._base_qs()
        qs_filtered = ProjectsDashboardService._apply_filters(qs, tid=tid, company_id=company_id, query=query)
        qs_annotated = ProjectsDashboardService._annotate_metrics(qs_filtered)

        # các filter cần annotation
        if query.health_min is not None:
            qs_annotated = qs_annotated.filter(_health_sort__gte=int(query.health_min))
        if query.health_max is not None:
            qs_annotated = qs_annotated.filter(_health_sort__lte=int(query.health_max))
        if query.shops_min is not None:
            qs_annotated = qs_annotated.filter(_shops_total__gte=int(query.shops_min))
        if query.shops_max is not None:
            qs_annotated = qs_annotated.filter(_shops_total__lte=int(query.shops_max))

        return JsonResponse({"ok": True, "total": qs_annotated.count()})

    result = ProjectsDashboardService.build(
        tid=tid,
        company_id=company_id,
        query=query,
        is_founder=founder_role,
    )

    ctx = {
        "tenant_id": tid,
        "role_label": role_label,
        "companies": companies,
        "selected_company_id": company_id,
        "summary": result["summary"],
        "items": result["items"],
        "founder_extra": result.get("founder_extra"),
        "page_obj": result["page_obj"],
        "paginator": result["paginator"],
        "filters": query.__dict__,
        "sort": query.sort,
        "dir": query.direction,
        "qs_keep": keep_querystring(request, drop=["page"]),
    }
    return render(request, TEMPLATE_PAGE, ctx)


@login_required
def projects_dashboard_export_csv(request):
    """
    Export CSV theo filter hiện tại.
    Level 9: truyền user_id để rate-limit + audit chuẩn.
    """
    tid = current_tenant_id(request)
    if not tid:
        return render(
            request,
            TEMPLATE_PAGE,
            {"error": "Thiếu ngữ cảnh tenant (tenant_id)."},
            status=400,
        )
    tid = int(tid)

    companies = companies_for_user(tid, request.user)
    company_id = resolve_company_id_for_page(request, tid, companies)

    founder_role = is_founder_user(request.user)
    if (not founder_role) and (company_id is None):
        return render(
            request,
            TEMPLATE_PAGE,
            {"error": "Bạn chưa có Company đang hoạt động trong tenant này."},
            status=403,
        )

    query = ProjectsDashboardQuery.from_request(request)

    return ProjectsDashboardService.export_csv_response(
        tid=tid,
        company_id=company_id,
        query=query,
        user_id=getattr(request.user, "id", None),
    )


@login_required
@require_POST
def projects_dashboard_bulk_update(request):
    """
    Bulk update (Level 9)
    - Tick từng dòng -> project_ids[]
    - Áp dụng tất cả theo bộ lọc -> select_all_filtered=1
    Level 9: truyền user_id để rate-limit + audit chuẩn.
    """
    tid = current_tenant_id(request)
    if not tid:
        messages.error(request, "Thiếu ngữ cảnh tenant (tenant_id).")
        return redirect("dashboard_projects:projects_dashboard")
    tid = int(tid)

    companies = companies_for_user(tid, request.user)
    company_id = resolve_company_id_for_page(request, tid, companies)

    founder_role = is_founder_user(request.user)
    if (not founder_role) and (company_id is None):
        messages.error(request, "Bạn chưa có Company đang hoạt động trong tenant này.")
        return redirect("dashboard_projects:projects_dashboard")

    ids = request.POST.getlist("project_ids")
    select_all_filtered = (request.POST.get("select_all_filtered") or "").strip() == "1"

    new_status = (request.POST.get("bulk_status") or "").strip() or None
    new_type = (request.POST.get("bulk_type") or "").strip() or None

    if (not new_status) and (not new_type):
        messages.error(request, "Bạn chưa chọn 'Trạng thái mới' hoặc 'Loại mới' để cập nhật.")
        back = request.POST.get("back") or request.META.get("HTTP_REFERER") or ""
        return redirect(back or "dashboard_projects:projects_dashboard")

    query = ProjectsDashboardQuery.from_request(request)

    result = ProjectsDashboardService.bulk_update(
        tid=tid,
        company_id=company_id,
        project_ids=ids,
        new_status=new_status,
        new_type=new_type,
        select_all_filtered=select_all_filtered,
        query=query,
        user_id=getattr(request.user, "id", None),
    )

    if result.get("ok"):
        messages.success(request, result.get("message") or "Cập nhật thành công.")
    else:
        messages.error(request, result.get("message") or "Cập nhật thất bại.")

    back = request.POST.get("back") or request.META.get("HTTP_REFERER") or ""
    return redirect(back or "dashboard_projects:projects_dashboard")