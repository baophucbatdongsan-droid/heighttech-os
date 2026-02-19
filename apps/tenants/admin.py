# apps/tenants/admin.py
from django.contrib import admin
from apps.tenants.models import Agency, Tenant, TenantDomain


@admin.register(Agency)
class AgencyAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_active", "created_at")
    search_fields = ("name",)
    list_filter = ("is_active",)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "agency", "is_active", "created_at", "updated_at")
    search_fields = ("name",)
    list_filter = ("is_active", "agency")


@admin.register(TenantDomain)
class TenantDomainAdmin(admin.ModelAdmin):
    list_display = ("id", "domain", "tenant", "is_primary", "is_active", "updated_at")
    search_fields = ("domain",)
    list_filter = ("is_active", "is_primary")