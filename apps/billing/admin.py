from __future__ import annotations

from django.contrib import admin
from django.db.models import QuerySet

from apps.billing.models import TenantUsageDaily, TenantUsageMonthly, Invoice
from apps.billing.services.payment import mark_invoice_paid


# ==========================================================
# Helpers (field-safe)
# ==========================================================

def _tenant_id(obj) -> int | str:
    # hỗ trợ cả tenant FK và tenant_id int
    if hasattr(obj, "tenant_id") and getattr(obj, "tenant_id") is not None:
        return getattr(obj, "tenant_id")
    tenant = getattr(obj, "tenant", None)
    if tenant is not None and getattr(tenant, "id", None) is not None:
        return tenant.id
    return "-"


def _tenant_name(obj) -> str:
    tenant = getattr(obj, "tenant", None)
    if tenant is not None:
        return getattr(tenant, "name", "") or f"Tenant#{getattr(tenant, 'id', '-')}"
    tid = _tenant_id(obj)
    return f"Tenant#{tid}" if tid != "-" else "-"


def _year(obj) -> int | str:
    if hasattr(obj, "year") and getattr(obj, "year", None) is not None:
        return getattr(obj, "year")
    m = getattr(obj, "month", None)
    return getattr(m, "year", "-") if m else "-"


def _month(obj) -> int | str:
    m = getattr(obj, "month", None)
    if isinstance(m, int):
        return m
    return getattr(m, "month", "-") if m else "-"


def _period(obj) -> str:
    ps = getattr(obj, "period_start", None)
    pe = getattr(obj, "period_end", None)
    if ps and pe:
        return f"{ps} → {pe}"
    y = _year(obj)
    mo = _month(obj)
    if y != "-" and mo != "-":
        return f"{y}-{int(mo):02d}"
    return "-"


def _updated_at(obj):
    return getattr(obj, "updated_at", None) or getattr(obj, "created_at", None)


def _has_fk_tenant(model_cls) -> bool:
    # kiểm tra model có field "tenant" FK không
    try:
        model_cls._meta.get_field("tenant")
        return True
    except Exception:
        return False


# ==========================================================
# Admin actions
# ==========================================================

@admin.action(description="Mark selected invoices as PAID")
def mark_paid(modeladmin, request, queryset: QuerySet[Invoice]):
    # xử lý theo batch, nhưng vẫn gọi service để audit + logic tenant status
    for inv in queryset:
        mark_invoice_paid(inv)


# ==========================================================
# TenantUsageDaily
# ==========================================================

@admin.register(TenantUsageDaily)
class TenantUsageDailyAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "tenant_col",
        "tenant_name_col",
        "requests",
        "errors",
        "slow",
        "rate_limited",
        "updated_col",
    )
    list_filter = ("date",)
    date_hierarchy = "date"
    ordering = ("-date", "-id")
    list_per_page = 50

    def get_search_fields(self, request):
        # nếu model dùng tenant FK: search tenant__id và tenant__name
        if _has_fk_tenant(TenantUsageDaily):
            return ("tenant__id", "tenant__name")
        return ("tenant_id",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if _has_fk_tenant(TenantUsageDaily):
            return qs.select_related("tenant")
        return qs

    @admin.display(description="tenant_id")
    def tenant_col(self, obj):
        return _tenant_id(obj)

    @admin.display(description="tenant")
    def tenant_name_col(self, obj):
        return _tenant_name(obj)

    @admin.display(description="updated_at")
    def updated_col(self, obj):
        return _updated_at(obj)


# ==========================================================
# TenantUsageMonthly
# ==========================================================

@admin.register(TenantUsageMonthly)
class TenantUsageMonthlyAdmin(admin.ModelAdmin):
    list_display = (
        "period_col",
        "tenant_col",
        "tenant_name_col",
        "requests",
        "errors",
        "slow",
        "rate_limited",
        "updated_col",
    )
    ordering = ("-id",)
    list_per_page = 50

    def get_list_filter(self, request):
        lf = []
        # chỉ add nếu field tồn tại thật
        if hasattr(TenantUsageMonthly, "year"):
            lf.append("year")
        if hasattr(TenantUsageMonthly, "month"):
            lf.append("month")
        return tuple(lf)

    def get_search_fields(self, request):
        if _has_fk_tenant(TenantUsageMonthly):
            return ("tenant__id", "tenant__name")
        return ("tenant_id",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if _has_fk_tenant(TenantUsageMonthly):
            return qs.select_related("tenant")
        return qs

    @admin.display(description="period")
    def period_col(self, obj):
        return _period(obj)

    @admin.display(description="tenant_id")
    def tenant_col(self, obj):
        return _tenant_id(obj)

    @admin.display(description="tenant")
    def tenant_name_col(self, obj):
        return _tenant_name(obj)

    @admin.display(description="updated_at")
    def updated_col(self, obj):
        return _updated_at(obj)


# ==========================================================
# Invoice
# ==========================================================

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "period_col",
        "tenant_col",
        "tenant_name_col",
        "total_amount",
        "currency",
        "status",
        "updated_col",
    )
    ordering = ("-id",)
    list_per_page = 50
    readonly_fields = ("usage_snapshot", "line_items", "created_at", "updated_at")
    actions = [mark_paid]

    def get_list_filter(self, request):
        lf = ["status"]
        if hasattr(Invoice, "year"):
            lf.insert(0, "year")
        if hasattr(Invoice, "month"):
            # đảm bảo month đứng sau year nếu có
            idx = 1 if "year" in lf else 0
            lf.insert(idx, "month")
        return tuple(lf)

    def get_search_fields(self, request):
        if _has_fk_tenant(Invoice):
            return ("tenant__id", "tenant__name")
        return ("tenant_id",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if _has_fk_tenant(Invoice):
            return qs.select_related("tenant")
        return qs

    @admin.display(description="period")
    def period_col(self, obj):
        return _period(obj)

    @admin.display(description="tenant_id")
    def tenant_col(self, obj):
        return _tenant_id(obj)

    @admin.display(description="tenant")
    def tenant_name_col(self, obj):
        return _tenant_name(obj)

    @admin.display(description="updated_at")
    def updated_col(self, obj):
        return _updated_at(obj)