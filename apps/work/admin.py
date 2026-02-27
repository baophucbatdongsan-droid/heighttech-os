from __future__ import annotations

from django.contrib import admin

from apps.work.models import WorkItem, WorkComment


@admin.register(WorkItem)
class WorkItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tenant_id",
        "title",
        "status",
        "priority",
        "company_id",
        "project_id",
        "target_type",
        "target_id",
        "assignee_id",
        "requester_id",
        "due_at",
        "updated_at",
    )
    list_filter = ("status", "priority", "target_type")
    search_fields = ("title", "description", "target_type", "target_id")
    readonly_fields = ("created_at", "updated_at", "started_at", "done_at")


@admin.register(WorkComment)
class WorkCommentAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant_id", "work_item_id", "actor_id", "created_at")
    search_fields = ("body",)
    readonly_fields = ("created_at",)