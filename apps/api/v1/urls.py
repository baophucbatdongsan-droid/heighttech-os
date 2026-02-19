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

# OPS
from .ops_health import FounderOpsHealthApi
from .ops_owners import FounderOpsOwnerPerformanceApi
# apps/api/v1/urls.py
from .founder_projects_dashboard import FounderProjectsDashboardApi

# ACTIONS V1 + V2
from .actions import (
    FounderActionsApi,
    FounderActionUpdateApi,
    FounderActionListV2Api,
    FounderActionDetailApi,
    FounderActionBulkUpdateV2Api,
    FounderActionEscalateV2Api,
)

# SNAPSHOTS
from .founder_insights import FounderSnapshotListApi, FounderSnapshotDetailApi

from .projects_dashboard import ProjectsDashboardApi


urlpatterns = [
    path("", ApiV1Root.as_view(), name="api_v1_root"),

    # DASHBOARD
    path("dashboard/", DashboardApi.as_view(), name="api_v1_dashboard"),

    # FOUNDER
    path("founder/", FounderDashboardApi.as_view(), name="api_v1_founder_dashboard"),
    path("founder/shops/<int:shop_id>/", FounderShopDetailApi.as_view(), name="api_v1_founder_shop_detail"),

    # IMPORT
    path("import/monthly-performance/", ImportMonthlyPerformanceApi.as_view(), name="api_v1_import_monthly_performance"),

    # SYSTEM
    path("system/health/", SystemHealthApi.as_view(), name="api_v1_system_health"),
    path("founder/insight/", FounderInsightApi.as_view(), name="api_v1_founder_insight"),

    # CLIENT
    path("client/dashboard/", ClientDashboardApi.as_view(), name="api_v1_client_dashboard"),

    # ACTIONS V1
    path("founder/actions/", FounderActionsApi.as_view(), name="api_v1_actions"),
    path("founder/actions/<int:action_id>/", FounderActionUpdateApi.as_view(), name="api_v1_action_update"),

    # ACTIONS V2
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

    # PROJECTS (include)
    path("", include("apps.api.v1.urls_projects")),
    path("founder/projects/dashboard/", FounderProjectsDashboardApi.as_view(), name="api_v1_founder_projects_dashboard"),
    path("projects/dashboard/", ProjectsDashboardApi.as_view(), name="api_v1_projects_dashboard"),
    path("", include("apps.api.v1.urls_projects")),
]
