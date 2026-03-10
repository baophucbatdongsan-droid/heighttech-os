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
from apps.api.v1.team import TeamListApi, TeamCreateApi
from apps.api.v1.contracts import ContractListApi, ContractCreateApi, ContractDetailApi
from apps.api.v1.contracts_center import (
    ContractDetailCenterApi,
    ContractMilestoneCreateApi,
    ContractPaymentCreateApi,
    ContractBookingCreateApi,
    ContractMilestoneDoneApi,
    ContractPaymentMarkPaidApi,
    ContractBookingMarkAiredApi,
    ContractBookingMarkPayoutPaidApi,
)
from apps.api.v1.contracts_client import ClientContractChannelProgressApi
from apps.api.v1.contracts_channel_admin import (
    ChannelContentListApi,
    ChannelContentCreateApi,
    ChannelContentUpdateApi,
    ChannelContentMetricUpdateApi,
)
from apps.api.v1.contracts_content_ai import ContentAiScoreApi
from apps.api.v1.founder_content_ai_dashboard import FounderContentAiDashboardApi
from apps.api.v1.founder_content_priority_dashboard import FounderContentPriorityDashboardApi
from apps.api.v1.founder_content_auto_tasks import FounderContentAutoTasksGenerateApi
from apps.api.v1.content_work_sync import ContentSyncFromWorkItemApi
from apps.api.v1.founder_content_recompute import FounderContentRecomputeApi
from apps.api.v1.founder_assignment_preview import FounderAssignmentPreviewApi

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

    # WORK-ITEM transition
    path("work-items/<int:workitem_id>/transition/", WorkItemTransitionApi.as_view(), name="workitem-transition"),

    # OS
    path("os/", include(("apps.api.v1.os.urls", "api_v1_os"), namespace="api_v1_os")),

    # TEAM
    path("team/", TeamListApi.as_view(), name="api_v1_team_list"),
    path("team/create/", TeamCreateApi.as_view(), name="api_v1_team_create"),

    # CONTRACTS

    path("contracts/", ContractListApi.as_view(), name="api_v1_contracts"),
    path("contracts/create/", ContractCreateApi.as_view(), name="api_v1_contracts_create"),
    path("contracts/<int:contract_id>/", ContractDetailApi.as_view(), name="api_v1_contracts_detail"),
    path("contracts/<int:contract_id>/center/", ContractDetailCenterApi.as_view(), name="api_v1_contract_center"),
    path("contracts/<int:contract_id>/milestones/create/", ContractMilestoneCreateApi.as_view(), name="api_v1_contract_milestone_create"),
    path("contracts/<int:contract_id>/payments/create/", ContractPaymentCreateApi.as_view(), name="api_v1_contract_payment_create"),
    path("contracts/<int:contract_id>/bookings/create/", ContractBookingCreateApi.as_view(), name="api_v1_contract_booking_create"),
    path("contracts/<int:contract_id>/milestones/<int:milestone_id>/done/", ContractMilestoneDoneApi.as_view(), name="api_v1_contract_milestone_done"),
    path("contracts/<int:contract_id>/payments/<int:payment_id>/mark-paid/", ContractPaymentMarkPaidApi.as_view(), name="api_v1_contract_payment_mark_paid"),
    path("contracts/<int:contract_id>/bookings/<int:booking_id>/mark-aired/", ContractBookingMarkAiredApi.as_view(), name="api_v1_contract_booking_mark_aired"),
    path("contracts/<int:contract_id>/bookings/<int:booking_id>/mark-payout-paid/", ContractBookingMarkPayoutPaidApi.as_view(), name="api_v1_contract_booking_mark_payout_paid"),
    path("contracts/<int:contract_id>/client/channel-progress/", ClientContractChannelProgressApi.as_view(), name="api_v1_client_contract_channel_progress"),
    path("contracts/<int:contract_id>/channel-content/", ChannelContentListApi.as_view()),
    path("contracts/<int:contract_id>/channel-content/create/", ChannelContentCreateApi.as_view()),
    path("channel-content/<int:content_id>/update/", ChannelContentUpdateApi.as_view()),
    path("channel-content/<int:content_id>/metric/", ChannelContentMetricUpdateApi.as_view()),
    path("channel-content/<int:content_id>/ai-score/", ContentAiScoreApi.as_view()),
    path("founder/content-ai-dashboard/", FounderContentAiDashboardApi.as_view(), name="api_v1_founder_content_ai_dashboard"),
    path("founder/content-priority-dashboard/", FounderContentPriorityDashboardApi.as_view(), name="api_v1_founder_content_priority_dashboard"),
    path("founder/content-auto-tasks/generate/", FounderContentAutoTasksGenerateApi.as_view(), name="api_v1_founder_content_auto_tasks_generate"),
    path("work-items/<int:workitem_id>/sync-content/", ContentSyncFromWorkItemApi.as_view(), name="api_v1_workitem_sync_content"),
    path("founder/content-recompute/", FounderContentRecomputeApi.as_view(), name="api_v1_founder_content_recompute"),
    path("founder/assignment-preview/", FounderAssignmentPreviewApi.as_view(), name="api_v1_founder_assignment_preview"),
    path("shops/", include(("apps.api.v1.shops.urls", "api_v1_shops"), namespace="api_v1_shops")),
    path("accounts/", include("apps.api.v1.accounts.urls")),

    # KEEP THIS LAST
    path("", include("apps.api.v1.urls_projects")),
]
