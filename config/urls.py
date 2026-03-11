from __future__ import annotations

from django.contrib import admin
from django.shortcuts import redirect, render
from django.urls import include, path
from django.views.generic import TemplateView

from apps.core.views_metrics import metrics_view
from apps.os.views import (
    content_work_sync_page,
    contract_channel_content_page,
    contract_client_progress_page,
    contract_detail_page,
    contracts_page,
    founder_content_ai_dashboard_page,
    founder_content_priority_dashboard_page,
    shops_page,
    sku_page,
)
from apps.os.views_partners import PartnerCreateView, PartnerListView
from apps.sales.views_client_sales import client_sales_home
from apps.work.views_client import client_work_home
from apps.os.views_company import company_workspace_page


admin.site.site_header = "HeightTech OS"
admin.site.site_title = "HeightTech OS"
admin.site.index_title = "Bảng điều hành hệ thống HeightTech"


def root_view(request):
    user = getattr(request, "user", None)

    if user and getattr(user, "is_authenticated", False):
        return redirect("/os/")

    return render(request, "auth/root_landing.html")


urlpatterns = [
    path("", root_view),
    path("admin/", admin.site.urls),

    # auth
    path("", include("apps.accounts.urls_auth")),

    # core / misc
    path("", include("apps.core.urls")),
    path("", include("apps.intelligence.urls")),

    # workspace
    path("app/", include("apps.dashboard.urls_app")),

    # dashboards
    path(
        "dashboard/",
        include(
            ("apps.dashboard.urls_projects", "dashboard_projects"),
            namespace="dashboard_projects",
        ),
    ),
    path("dashboard/", include("apps.dashboard.urls")),

    # founder
    path("founder/", include("apps.dashboard.urls_founder")),

    # api
    path("api/", include("apps.api.urls")),

    # metrics
    path("metrics/", metrics_view),

    # work / sales
    path("work/", include(("apps.work.urls", "work"), namespace="work")),
    path("client/work/", client_work_home),
    path("client/sales/", client_sales_home),
    path("sales/", include(("apps.sales.urls", "sales"), namespace="sales")),

    # OS UI
    path("os/", TemplateView.as_view(template_name="os/index.html"), name="os_ui"),
    path("os/team/", TemplateView.as_view(template_name="os_team.html"), name="os_team"),
    path("os/contracts/", contracts_page, name="os_contracts"),
    path("os/contracts/<int:contract_id>/", contract_detail_page, name="os_contract_detail"),
    path(
        "os/contracts/<int:contract_id>/client/shop/<int:shop_id>/progress/",
        contract_client_progress_page,
        name="os_contract_client_progress",
    ),
    path(
        "os/contracts/<int:contract_id>/content/",
        contract_channel_content_page,
        name="os_contract_channel_content",
    ),

    path("os/shops/", shops_page, name="os_shops"),

    path("os/sku/", sku_page, name="os_sku"),

    path("os/partners/", PartnerListView.as_view(), name="os_partners"),
    path("os/partners/new/", PartnerCreateView.as_view(), name="os_partner_new"),

    path(
        "os/founder/content-ai/",
        founder_content_ai_dashboard_page,
        name="os_founder_content_ai_dashboard",
    ),
    path(
        "os/founder/content-priority/",
        founder_content_priority_dashboard_page,
        name="os_founder_content_priority_dashboard",
    ),
    path(
        "os/content-work-sync/",
        content_work_sync_page,
        name="os_content_work_sync",
    ),
    path(
        "os/company/<int:company_id>/",
        company_workspace_page,
        name="os_company_workspace",
    ),
]