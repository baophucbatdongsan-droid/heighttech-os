from django.urls import path

from apps.api.v1.os.views_entity_attachment import (
    OSEntityAttachmentListApi,
    OSEntityAttachmentUploadApi,
    OSEntityAttachmentDownloadApi,
    OSEntityAttachmentPreviewApi,
)

urlpatterns = [
    path(
        "attachments/<str:target_type>/<int:target_id>/",
        OSEntityAttachmentListApi.as_view(),
        name="api_v1_os_attachment_list",
    ),
    path(
        "attachments/<str:target_type>/<int:target_id>/upload/",
        OSEntityAttachmentUploadApi.as_view(),
        name="api_v1_os_attachment_upload",
    ),
    path(
        "attachments/<int:attachment_id>/download/",
        OSEntityAttachmentDownloadApi.as_view(),
        name="api_v1_os_attachment_download",
    ),
    path(
        "attachments/<int:attachment_id>/preview/",
        OSEntityAttachmentPreviewApi.as_view(),
        name="api_v1_os_attachment_preview",
    ),
]