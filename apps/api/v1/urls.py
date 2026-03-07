# apps/api/v1/urls.py
from __future__ import annotations

from django.urls import include, path

from .views import ApiV1Root
from .dashboard import DashboardApi
from .founder import FounderDashboardApi, FounderShopDetailApi
from .imports import ImportMonthlyPerformanceApi
from .system import SystemHealthApi
from .insight import FounderInsightApi
from .client import ClientDashboardApi

from .ops_health import FounderOpsHealthApi
from .ops_owners import FounderOpsOwnerPerformanceApi
from .founder_ops import FounderOpsOverviewApi

from .founder_projects_dashboard import FounderProjectsDashboardApi
from .projects_dashboard import ProjectsDashboardApi

from .actions import (
    FounderActionsApi,
    FounderActionUpdateApi,
    FounderActionListV2Api,
    FounderActionDetailApi,
    FounderActionBulkUpdateV2Api,
    FounderActionEscalateV2Api,
)

from .founder_insights import FounderSnapshotListApi, FounderSnapshotDetailApi

from apps.api.v1.work.workitems import WorkItemTransitionApi

urlpatterns = [
    path("", ApiV1Root.as_view(), name="api_v1_root"),

    path("dashboard/", DashboardApi.as_view(), name="api_v1_dashboard"),

    path("founder/", FounderDashboardApi.as_view(), name="api_v1_founder_dashboard"),
    path("founder/shops/<int:shop_id>/", FounderShopDetailApi.as_view(), name="api_v1_founder_shop_detail"),
    path("founder/insight/", FounderInsightApi.as_view(), name="api_v1_founder_insight"),

    path("import/monthly-performance/", ImportMonthlyPerformanceApi.as_view(), name="api_v1_import_monthly_performance"),
    path("system/health/", SystemHealthApi.as_view(), name="api_v1_system_health"),
    path("client/dashboard/", ClientDashboardApi.as_view(), name="api_v1_client_dashboard"),

    # ACTIONS
    path("founder/actions/", FounderActionsApi.as_view(), name="api_v1_actions"),
    path("founder/actions/<int:action_id>/", FounderActionUpdateApi.as_view(), name="api_v1_action_update"),

    path("founder/actions/v2/", FounderActionListV2Api.as_view(), name="api_v1_actions_v2_list"),
    path("founder/actions/v2/<int:action_id>/", FounderActionDetailApi.as_view(), name="api_v1_actions_v2_detail"),
    path("founder/actions/v2/bulk/", FounderActionBulkUpdateV2Api.as_view(), name="api_v1_actions_v2_bulk"),
    path("founder/actions/v2/escalate/", FounderActionEscalateV2Api.as_view(), name="api_v1_actions_v2_escalate"),

    # SNAPSHOTS
    path("founder/snapshots/", FounderSnapshotListApi.as_view(), name="api_v1_snapshot_list"),
    path("founder/snapshots/<int:snapshot_id>/", FounderSnapshotDetailApi.as_view(), name="api_v1_snapshot_detail"),

    # OPS
    path("founder/ops/health/", FounderOpsHealthApi.as_view(), name="api_v1_ops_health"),
    path("founder/ops/owners/performance/", FounderOpsOwnerPerformanceApi.as_view(), name="api_v1_ops_owner_performance"),
    path("founder/ops/overview/", FounderOpsOverviewApi.as_view(), name="api_v1_founder_ops_overview"),

    # PROJECTS
    path("founder/projects/dashboard/", FounderProjectsDashboardApi.as_view(), name="api_v1_founder_projects_dashboard"),
    path("projects/dashboard/", ProjectsDashboardApi.as_view(), name="api_v1_projects_dashboard"),

    # BILLING
    path("billing/", include(("apps.api.v1.billing.urls", "api_v1_billing"), namespace="api_v1_billing")),

    # WORK
    path("work/", include("apps.api.v1.work.urls")),

    # SHOPS
    path("shops/", include(("apps.api.v1.shops.urls", "api_v1_shops"), namespace="api_v1_shops")),

    # WORK-ITEM transition (đặt trước include "" nếu có)
    path("work-items/<int:workitem_id>/transition/", WorkItemTransitionApi.as_view(), name="workitem-transition"),

    # ✅ OS gom 1 cục duy nhất
    path("os/", include(("apps.api.v1.os.urls", "api_v1_os"), namespace="api_v1_os")),

    # ✅ include "" để CUỐI (rất quan trọng)
    path("", include("apps.api.v1.urls_projects")),
]