from __future__ import annotations

from django.urls import path
from django.views.generic import RedirectView, TemplateView
from apps.os.views import file_viewer_page
from apps.os.views import (
    client_work_page,
    content_work_sync_page,
    contract_channel_content_page,
    contract_client_progress_page,
    contract_detail_page,
    contracts_page,
    founder_content_ai_dashboard_page,
    founder_content_priority_dashboard_page,
    os_team_page,
    shops_page,
    sku_page,
    work_page,
)
from apps.os.views_company import company_workspace_page
from apps.os.views_partners import PartnerCreateView, PartnerListView
from apps.os.views import (
    content_work_sync_page,
    contract_channel_content_page,
    contract_client_progress_page,
    contract_detail_page,
    contracts_page,
    file_viewer_page,
    founder_content_ai_dashboard_page,
    founder_content_priority_dashboard_page,
    os_team_page,
    shops_page,
    sku_page,
    work_page,
    client_work_page,
)
from apps.os.views_sheets import sheets_page, sheet_detail_page
from apps.docs.views import docs_page, doc_detail_page

app_name = "os"

urlpatterns = [
    # home
    path("os/", TemplateView.as_view(template_name="os/index.html"), name="os_ui"),

    # workspaces
    path("work/", work_page, name="work_page"),
    path("client/work/", client_work_page, name="client_work_page"),
    path("os/team/", os_team_page, name="os_team"),

    # contracts
    path("os/contracts/", contracts_page, name="os_contracts"),
    path("os/contracts/<int:contract_id>/", contract_detail_page, name="os_contract_detail"),
    path(
        "os/contracts/<int:contract_id>/client/shop/<int:shop_id>/progress/",
        contract_client_progress_page,
        name="os_contract_client_progress",
    ),
    path(
        "os/contracts/<int:contract_id>/channel-content/",
        contract_channel_content_page,
        name="os_contract_channel_content",
    ),

    # legacy compatibility -> redirect sạch
    path(
        "os/contracts/<int:contract_id>/content/",
        RedirectView.as_view(pattern_name="os:os_contract_channel_content", permanent=False),
        name="os_contract_channel_content_legacy",
    ),

    # other OS modules
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
    path("os/files/<int:attachment_id>/", file_viewer_page, name="os_file_viewer"),

    path("os/sheets/", sheets_page, name="sheets-page"),
    path("os/sheets/<int:sheet_id>/", sheet_detail_page, name="sheet-detail-page"),
    path("os/docs/", docs_page, name="docs-page"),
    path("os/docs/<int:doc_id>/", doc_detail_page, name="doc-detail-page"),
]