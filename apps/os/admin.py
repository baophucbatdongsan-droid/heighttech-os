from __future__ import annotations

from django.contrib import admin

from apps.os.models_attachment import OSAttachment


@admin.register(OSAttachment)
class OSAttachmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tenant_id",
        "target_type",
        "target_id",
        "original_name",
        "content_type",
        "file_size",
        "uploaded_by",
        "created_at",
        "is_deleted",
    )
    list_filter = (
        "tenant_id",
        "target_type",
        "content_type",
        "is_deleted",
        "created_at",
    )
    search_fields = (
        "original_name",
        "file_name",
    )
    readonly_fields = (
        "file_size",
        "created_at",
        "updated_at",
    )