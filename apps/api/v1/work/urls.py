# apps/api/v1/work/urls.py
from __future__ import annotations

from django.urls import path

from .views import (
    WorkItemListCreateView,
    WorkItemDetailView,
    WorkItemAddCommentView,
    WorkItemTimelineView,
    WorkMySummaryView,
    WorkBoardView,
    WorkItemMoveView,
    WorkPortalSummaryView,
)

from . import views_analytics as va
from .views_dashboard import WorkDashboardV1View


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
    path("items/", WorkItemListCreateView.as_view(), name="work_item_list_create"),
    path("items/<int:pk>/", WorkItemDetailView.as_view(), name="work_item_detail"),

    path("items/<int:pk>/comment/", WorkItemAddCommentView.as_view(), name="work_item_add_comment"),
    path("items/<int:pk>/comments/", WorkItemAddCommentView.as_view(), name="work_item_add_comment_plural"),

    path("items/<int:pk>/timeline/", WorkItemTimelineView.as_view(), name="work_item_timeline"),

    path("my-summary/", WorkMySummaryView.as_view(), name="work_my_summary"),

    path("board/", WorkBoardView.as_view(), name="work_board"),
    path("items/<int:pk>/move/", WorkItemMoveView.as_view(), name="workitem-move"),

    path("portal/summary/", WorkPortalSummaryView.as_view(), name="work_portal_summary"),
]


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

urlpatterns.append(path("analytics/dashboard/v1/", WorkDashboardV1View.as_view(), name="work_analytics_dashboard_v1"))