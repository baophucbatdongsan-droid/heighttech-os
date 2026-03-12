from __future__ import annotations

from django.contrib import admin

from apps.work.models import WorkItem, WorkItemTransitionLog
from apps.work.models_attachment import TaskAttachment
from apps.work.models_comment import WorkComment


@admin.register(WorkItem)
class WorkItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tenant",
        "title",
        "status",
        "priority",
        "company",
        "project",
        "assignee",
        "due_at",
        "position",
        "updated_at",
    )
    list_filter = ("tenant", "status", "priority", "is_internal")
    search_fields = ("title", "description")
    readonly_fields = ("created_at", "updated_at", "started_at", "done_at")
    autocomplete_fields = ("company", "project", "assignee", "requester", "created_by")


@admin.register(WorkComment)
class WorkCommentAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "work_item", "actor", "created_at")
    search_fields = ("body", "work_item__title", "actor__username", "actor__email")
    list_filter = ("tenant", "created_at")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("work_item", "actor")


@admin.register(WorkItemTransitionLog)
class WorkItemTransitionLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tenant",
        "workitem",
        "from_status",
        "to_status",
        "workflow_version",
        "actor",
        "created_at",
    )
    list_filter = ("tenant", "workflow_version")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("workitem", "actor", "company", "project")


@admin.register(TaskAttachment)
class TaskAttachmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tenant_id",
        "task",
        "original_name",
        "content_type",
        "file_size",
        "shop_id",
        "project_id",
        "uploaded_by",
        "created_at",
        "is_deleted",
    )
    list_filter = (
        "tenant_id",
        "content_type",
        "is_deleted",
        "created_at",
    )
    search_fields = (
        "original_name",
        "file_name",
        "task__title",
    )
    readonly_fields = (
        "file_size",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = (
        "task",
        "uploaded_by",
    )