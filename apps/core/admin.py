# apps/core/admin.py
from __future__ import annotations

import json
from typing import Any

from django.contrib import admin
from django.db.models import QuerySet
from django.utils.html import format_html

from apps.core.models import AuditLog
from apps.core.tenant_context import get_current_tenant


# ==========================================================
# MIXIN: Tenant scope cho admin
# ==========================================================

class TenantScopedAdminMixin:
    """
    - Admin chỉ thấy data của tenant hiện tại (middleware resolve).
    - Superuser (founder) nhìn được tất cả.
    """

    def _has_field(self, model, field: str) -> bool:
        try:
            return any(f.name == field for f in model._meta.get_fields())
        except Exception:
            return False

    def get_queryset(self, request) -> QuerySet:
        qs = super().get_queryset(request)

        if request.user.is_superuser:
            return qs

        Model = qs.model
        if not self._has_field(Model, "tenant"):
            return qs

        t = getattr(request, "tenant", None) or get_current_tenant()
        if not t:
            return qs.none()

        return qs.filter(tenant=t)


# ==========================================================
# Helpers: format JSON đẹp
# ==========================================================

def _pretty_json(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception:
        return str(data)


# ==========================================================
# AUDIT LOG ADMIN (CHỈ ĐĂNG KÝ 1 LẦN)
# ==========================================================

@admin.register(AuditLog)
class AuditLogAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """
    Audit log chỉ đọc.
    """

    list_display = (
        "id",
        "created_at",
        "tenant",
        "actor",
        "action",
        "target",
        "request_id",
        "trace_id",
        "ip_address",
        "method",
        "path",
    )

    list_filter = ("action", "app_label", "model_name", "created_at")

    search_fields = (
        "object_pk",
        "request_id",
        "trace_id",
        "actor__username",
        "actor__email",
        "path",
        "user_agent",
        "referer",
    )

    ordering = ("-created_at", "-id")

    readonly_fields = (
        "created_at",
        "tenant",
        "actor",
        "action",
        "app_label",
        "model_name",
        "object_pk",
        "request_id",
        "trace_id",
        "ip_address",
        "method",
        "path",
        "user_agent",
        "referer",
        "changed_fields",
        "before_pretty",
        "after_pretty",
        "meta_pretty",
    )

    fieldsets = (
        ("Thông tin chung", {
            "fields": (
                "created_at", "tenant", "actor", "action",
                "app_label", "model_name", "object_pk",
            )
        }),
        ("Request meta", {
            "fields": (
                "request_id",
                "trace_id",
                "ip_address",
                "method",
                "path",
                "user_agent",
                "referer",
            )
        }),
        ("Thay đổi", {
            "fields": (
                "changed_fields",
                "before_pretty",
                "after_pretty",
                "meta_pretty",
            )
        }),
    )

    # =========================
    # computed columns
    # =========================

    @admin.display(description="Đối tượng")
    def target(self, obj: AuditLog) -> str:
        return f"{obj.app_label}.{obj.model_name}#{obj.object_pk}"

    @admin.display(description="Trước (JSON)")
    def before_pretty(self, obj: AuditLog) -> str:
        return format_html(
            "<pre style='white-space:pre-wrap'>{}</pre>",
            _pretty_json(obj.before),
        )

    @admin.display(description="Sau (JSON)")
    def after_pretty(self, obj: AuditLog) -> str:
        return format_html(
            "<pre style='white-space:pre-wrap'>{}</pre>",
            _pretty_json(obj.after),
        )

    @admin.display(description="Meta (JSON)")
    def meta_pretty(self, obj: AuditLog) -> str:
        return format_html(
            "<pre style='white-space:pre-wrap'>{}</pre>",
            _pretty_json(obj.meta),
        )

    # =========================
    # read-only admin
    # =========================

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False