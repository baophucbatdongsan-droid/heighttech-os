# apps/api/v1/work/urls.py
from __future__ import annotations

from django.urls import path

from .views import (
    WorkItemListCreateView,
    WorkItemDetailView,
    WorkItemTimelineView,
    WorkItemAddCommentView,
    WorkMySummaryView,
    WorkPortalSummaryView,
    WorkBoardView,
    WorkItemMoveView,
    WorkItemAssignView,
)

from . import views_analytics as va
from .views_dashboard import WorkDashboardV1View

# OS workflow actions
from .workitems import WorkItemTransitionApi, WorkItemUpgradeWorkflowApi

app_name = "work"


# =========================================================
# helper: optional analytics view loader (không crash import)
# =========================================================
def _pick_view(*names):
    for n in names:
        v = getattr(va, n, None)
        if v is not None:
            return v
    return None


WorkloadAnalyticsView = _pick_view("WorkloadAnalyticsView", "WorkAnalyticsWorkloadView")
OverdueAnalyticsView = _pick_view("OverdueAnalyticsView", "WorkAnalyticsOverdueView")
VelocityAnalyticsView = _pick_view("VelocityAnalyticsView", "WorkAnalyticsVelocityView")

PerformanceByCompanyAnalyticsView = _pick_view(
    "PerformanceByCompanyAnalyticsView",
    "PerformanceCompanyAnalyticsView",
    "WorkAnalyticsPerformanceCompanyView",
)

WorkFounderDashboardView = _pick_view(
    "WorkFounderDashboardView",
    "WorkFounderDashboardV1View",
    "WorkAnalyticsDashboardView",
    "WorkAnalyticsDashboardV1View",
)


urlpatterns = [
    # =========================
    # WORK ITEMS CRUD
    # =========================
    path("items/", WorkItemListCreateView.as_view(), name="work_item_list_create"),
    path("items/<int:pk>/", WorkItemDetailView.as_view(), name="work_item_detail"),

    # =========================
    # COMMENTS + TIMELINE
    # =========================
    path("items/<int:pk>/comment/", WorkItemAddCommentView.as_view(), name="work_item_add_comment"),
    path("items/<int:pk>/comments/", WorkItemAddCommentView.as_view(), name="work_item_add_comment_plural"),
    path("items/<int:pk>/timeline/", WorkItemTimelineView.as_view(), name="work_item_timeline"),

    # =========================
    # BOARD + MOVE + ASSIGN
    # =========================
    path("board/", WorkBoardView.as_view(), name="work_board"),
    path("items/<int:pk>/move/", WorkItemMoveView.as_view(), name="work_item_move"),
    path("items/<int:pk>/assign/", WorkItemAssignView.as_view(), name="work_item_assign"),

    # =========================
    # USER SUMMARY + PORTAL
    # =========================
    path("my-summary/", WorkMySummaryView.as_view(), name="work_my_summary"),
    path("portal/summary/", WorkPortalSummaryView.as_view(), name="work_portal_summary"),

    # =========================
    # OS WORKFLOW ACTIONS
    # =========================
    path("items/<int:workitem_id>/transition/", WorkItemTransitionApi.as_view(), name="work_item_transition"),
    path(
        "items/<int:workitem_id>/upgrade-workflow/",
        WorkItemUpgradeWorkflowApi.as_view(),
        name="work_item_upgrade_workflow",
    ),
]


# =========================
# ANALYTICS (optional)
# =========================
if WorkloadAnalyticsView:
    urlpatterns.append(path("analytics/workload/", WorkloadAnalyticsView.as_view(), name="work_analytics_workload"))

if OverdueAnalyticsView:
    urlpatterns.append(path("analytics/overdue/", OverdueAnalyticsView.as_view(), name="work_analytics_overdue"))

if VelocityAnalyticsView:
    urlpatterns.append(path("analytics/velocity/", VelocityAnalyticsView.as_view(), name="work_analytics_velocity"))

if PerformanceByCompanyAnalyticsView:
    urlpatterns.append(
        path(
            "analytics/performance/company/",
            PerformanceByCompanyAnalyticsView.as_view(),
            name="work_analytics_performance_company",
        )
    )

if WorkFounderDashboardView:
    urlpatterns.append(path("analytics/dashboard/", WorkFounderDashboardView.as_view(), name="work_analytics_dashboard"))


# dashboard v1 (always available)
urlpatterns.append(path("analytics/dashboard/v1/", WorkDashboardV1View.as_view(), name="work_analytics_dashboard_v1"))