from __future__ import annotations

from django.contrib import admin

from apps.docs.models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tenant_id",
        "title",
        "doc_type",
        "linked_target_type",
        "linked_target_id",
        "created_by",
        "created_at",
        "is_deleted",
    )
    list_filter = ("doc_type", "tenant_id", "is_deleted", "linked_target_type")
    search_fields = ("title", "content_html", "public_token")
    readonly_fields = ("created_at", "updated_at", "public_token")
    autocomplete_fields = ("created_by",)