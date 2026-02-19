# apps/core/admin.py
from __future__ import annotations

from django.contrib import admin

from apps.core.models import AuditLog

from django.db.models import QuerySet

from apps.core.tenant_context import get_current_tenant


class TenantScopedAdminMixin:
    """
    - Admin chỉ thấy data của tenant hiện tại (middleware resolve).
    - Khi tạo mới auto gán tenant nếu model có field tenant.
    - Superuser (founder) nhìn được tất cả.
    """

    def _has_field(self, model, field: str) -> bool:
        try:
            return any(f.name == field for f in model._meta.get_fields())
        except Exception:
            return False

    def get_queryset(self, request) -> QuerySet:
        qs = super().get_queryset(request)

        # founder xem all
        if request.user.is_superuser:
            return qs

        Model = qs.model
        if not self._has_field(Model, "tenant"):
            return qs

        t = getattr(request, "tenant", None) or get_current_tenant()
        if not t:
            return qs.none()

        return qs.filter(tenant=t)

    def save_model(self, request, obj, form, change):
        # auto set tenant khi create
        if not request.user.is_superuser:
            if hasattr(obj, "tenant_id") and not getattr(obj, "tenant_id", None):
                t = getattr(request, "tenant", None) or get_current_tenant()
                if t:
                    obj.tenant = t
        return super().save_model(request, obj, form, change)

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "created_at",
        "actor",
        "action",
        "app_label",
        "model_name",
        "object_pk",
        "ip_address",
        "method",
        "path",
    )
    list_filter = ("action", "app_label", "model_name", "created_at")
    search_fields = ("object_pk", "actor__username", "actor__email", "path", "user_agent", "referer")
    readonly_fields = (
        "created_at",
        "actor",
        "action",
        "app_label",
        "model_name",
        "object_pk",
        "ip_address",
        "user_agent",
        "referer",
        "path",
        "method",
        "before",
        "after",
    )
    ordering = ("-created_at", "-id")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # log chỉ đọc
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class BaseCompanyAdmin(admin.ModelAdmin):
    """
    Admin chuẩn multi-company permission.
    Tất cả model có field `company` nên kế thừa class này.
    """

    def get_user_memberships(self, request):
        if not getattr(request.user, "is_authenticated", False):
            return []
        if not hasattr(request.user, "memberships"):
            return []
        return request.user.memberships.filter(is_active=True)

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        if request.user.is_superuser:
            return qs

        memberships = self.get_user_memberships(request)
        if not memberships or not memberships.exists():
            return qs.none()

        roles = set(memberships.values_list("role", flat=True))
        company_ids = list(memberships.values_list("company_id", flat=True))

        # Founder → full hệ thống
        if "founder" in roles:
            return qs

        # Head → full company
        if "head" in roles:
            return qs.filter(company_id__in=company_ids)

        # Account → filter theo account_manager (nếu model có field)
        if "account" in roles and hasattr(self.model, "account_manager_id"):
            return qs.filter(account_manager=request.user)

        # Operator → filter theo operator (nếu model có field)
        if "operator" in roles and hasattr(self.model, "operator_id"):
            return qs.filter(operator=request.user)

        # Mặc định → theo company
        if hasattr(self.model, "company_id"):
            return qs.filter(company_id__in=company_ids)

        # Model không có company_id thì chặn để tránh leak
        return qs.none()

    def save_model(self, request, obj, form, change):
        # Auto set company khi tạo mới (nếu model có field company)
        if not change and hasattr(obj, "company_id") and not getattr(obj, "company_id", None):
            memberships = self.get_user_memberships(request)
            membership = memberships.first() if memberships and hasattr(memberships, "first") else None
            if membership:
                obj.company = membership.company
        super().save_model(request, obj, form, change)