from __future__ import annotations

from django.contrib import admin
from django.db.models import QuerySet

from apps.core.tenant_context import get_current_tenant
from apps.shops.models import Shop, ShopMember


# =====================================================
# BASE TENANT ADMIN MIXIN
# =====================================================

class TenantAdminMixin:
    """
    - Founder (superuser) thấy tất cả
    - User thường chỉ thấy dữ liệu thuộc tenant hiện tại
    """

    def get_queryset(self, request) -> QuerySet:
        qs = super().get_queryset(request)

        if request.user.is_superuser:
            return qs

        tenant = get_current_tenant()
        if tenant and hasattr(qs.model, "tenant_id"):
            return qs.filter(tenant_id=tenant.id)

        return qs.none()

    def save_model(self, request, obj, form, change):
        """
        Auto gán tenant nếu chưa set.
        """
        if not obj.tenant_id:
            tenant = get_current_tenant()
            if tenant:
                obj.tenant = tenant
        super().save_model(request, obj, form, change)


# =====================================================
# SHOP ADMIN
# =====================================================

@admin.register(Shop)
class ShopAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "tenant",
        "name",
        "brand",
        "platform",
        "status",
        "is_active",
        "created_at",
    )

    list_filter = (
        "tenant",
        "status",
        "is_active",
        "platform",
    )

    search_fields = (
        "name",
        "code",
        "brand__name",
        "brand__company__name",
    )

    autocomplete_fields = ("brand",)
    ordering = ("-id",)

    readonly_fields = ("created_at", "updated_at")

    def get_list_filter(self, request):
        """
        Founder có filter tenant.
        User thường không cần.
        """
        if request.user.is_superuser:
            return self.list_filter
        return tuple(f for f in self.list_filter if f != "tenant")


# =====================================================
# SHOP MEMBER ADMIN
# =====================================================

@admin.register(ShopMember)
class ShopMemberAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "tenant",
        "shop",
        "user",
        "role",
        "is_active",
        "created_at",
    )

    list_filter = (
        "tenant",
        "role",
        "is_active",
    )

    search_fields = (
        "shop__name",
        "user__username",
        "user__email",
    )

    autocomplete_fields = ("shop", "user")
    ordering = ("-id",)

    readonly_fields = ("created_at",)

    def get_list_filter(self, request):
        if request.user.is_superuser:
            return self.list_filter
        return tuple(f for f in self.list_filter if f != "tenant")