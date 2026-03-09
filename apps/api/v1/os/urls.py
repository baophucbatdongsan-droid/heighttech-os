from django.urls import path

from .os_home import OSHomeApi
from .os_timeline import OSTimelineApi
from .os_notifications import OSNotificationsApi, OSNotificationMarkReadApi
from .os_command_center import OSCommandCenterApi
from .os_layout import OSLayoutApi
from .os_control_center import OSControlCenterApi
from .os_stream import os_stream_sse
from .os_work import (
    OSWorkInboxApi,
    OSWorkCreateApi,
    OSWorkAssignApi,
    OSWorkMoveApi,
    OSWorkUpdateApi,
    OSWorkCommentsApi,
    OSWorkQuickCreateApi,
)
from .os_work_assign_by import OSWorkAssignByApi
from apps.products.api_import import ProductCSVImportApi
from apps.products.api_stats import ProductDailyStatUpsertApi

app_name = "api_v1_os"

urlpatterns = [
    path("home/", OSHomeApi.as_view(), name="home"),
    path("layout/", OSLayoutApi.as_view(), name="layout"),
    path("timeline/", OSTimelineApi.as_view(), name="timeline"),
    path("notifications/", OSNotificationsApi.as_view(), name="notifications"),
    path(
        "notifications/<int:notification_id>/read/",
        OSNotificationMarkReadApi.as_view(),
        name="notification_read",
    ),
    path("stream/", os_stream_sse, name="stream"),
    path("control-center/", OSControlCenterApi.as_view(), name="control_center"),
    path("command-center/", OSCommandCenterApi.as_view(), name="command_center"),

    # Work OS
    path("work/inbox/", OSWorkInboxApi.as_view(), name="os_work_inbox"),
    path("work/create/", OSWorkCreateApi.as_view(), name="os_work_create"),
    path("work/<int:task_id>/assign/", OSWorkAssignApi.as_view(), name="os_work_assign"),
    path("work/assign-by/", OSWorkAssignByApi.as_view(), name="os_work_assign_by"),
    path("work/<int:task_id>/move/", OSWorkMoveApi.as_view(), name="os_work_move"),
    path("work/<int:task_id>/update/", OSWorkUpdateApi.as_view(), name="os_work_update"),
    path("work/quick-create/", OSWorkQuickCreateApi.as_view(), name="os_work_quick_create"),
    path("work/<int:task_id>/comments/", OSWorkCommentsApi.as_view(), name="os_work_comments"),
    path("products/import-csv/", ProductCSVImportApi.as_view(), name="products-import-csv"),
    path("products/daily-stats/upsert/", ProductDailyStatUpsertApi.as_view(), name="products-daily-stats-upsert"),
]