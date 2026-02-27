# apps/finance/admin.py
from __future__ import annotations

from django.contrib import admin, messages
from django.utils.html import format_html

from apps.finance.models import AgencyMonthlyFinance
from apps.finance.services import AgencyFinanceService


@admin.register(AgencyMonthlyFinance)
class AgencyMonthlyFinanceAdmin(admin.ModelAdmin):
    list_display = (
        "month",
        "status_badge",
        "total_gmv_fee_after_tax",
        "total_fixed_fee_net",
        "total_sale_commission",
        "total_team_bonus",
        "agency_net_profit",
        "calculated_at",
        "updated_at",
    )
    list_filter = ("status",)
    search_fields = ("month",)
    date_hierarchy = "month"
    ordering = ("-month",)

    readonly_fields = (
        "status",
        "total_gmv_fee_after_tax",
        "total_fixed_fee_net",
        "total_sale_commission",
        "total_team_bonus",
        "total_operating_cost",
        "agency_net_profit",
        "calculated_at",
        "locked_at",
        "finalized_at",
        "created_at",
        "updated_at",
    )

    actions = ("action_recalc", "action_lock", "action_finalize", "action_reopen")

    # =========================================
    # UI
    # =========================================
    def status_badge(self, obj: AgencyMonthlyFinance):
        color = "#999"
        if obj.status == AgencyMonthlyFinance.STATUS_OPEN:
            color = "#2ecc71"
        elif obj.status == AgencyMonthlyFinance.STATUS_LOCKED:
            color = "#f39c12"
        elif obj.status == AgencyMonthlyFinance.STATUS_FINALIZED:
            color = "#e74c3c"

        return format_html(
            '<span style="padding:2px 8px;border-radius:10px;background:{};color:white;font-weight:600;">{}</span>',
            color,
            obj.status.upper(),
        )

    status_badge.short_description = "Status"

    # =========================================
    # PERMISSIONS
    # =========================================
    def has_add_permission(self, request):
        # Snapshot tạo tự động qua service => chặn add tay để tránh sai
        return False

    def has_delete_permission(self, request, obj=None):
        # Không cho xoá snapshot trong admin (an toàn)
        return False

    def has_change_permission(self, request, obj=None):
        # Cho mở trang detail để xem, nhưng không cho sửa field (readonly_fields)
        return True

    # =========================================
    # ACTIONS
    # =========================================
    @admin.action(description="Recalculate snapshot (OPEN only)")
    def action_recalc(self, request, queryset):
        updated = 0
        skipped = 0

        for obj in queryset:
            if not obj.can_edit():
                skipped += 1
                continue
            AgencyFinanceService.calculate_or_update(obj.month)
            updated += 1

        if updated:
            self.message_user(request, f"✅ Recalculated {updated} month(s).", level=messages.SUCCESS)
        if skipped:
            self.message_user(
                request,
                f"⚠️ Skipped {skipped} month(s) vì đang LOCKED/FINALIZED.",
                level=messages.WARNING,
            )

    @admin.action(description="Lock selected month(s)")
    def action_lock(self, request, queryset):
        done = 0
        for obj in queryset:
            AgencyFinanceService.lock_month(obj.month)
            done += 1

        self.message_user(request, f"🔒 Locked {done} month(s).", level=messages.SUCCESS)

    @admin.action(description="Finalize selected month(s)")
    def action_finalize(self, request, queryset):
        done = 0
        for obj in queryset:
            AgencyFinanceService.finalize_month(obj.month)
            done += 1

        self.message_user(request, f"✅ Finalized {done} month(s).", level=messages.SUCCESS)

    @admin.action(description="Re-open selected month(s) (Superuser only)")
    def action_reopen(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(
                request,
                "❌ Chỉ Superuser mới được Re-open tháng.",
                level=messages.ERROR,
            )
            return

        done = 0
        for obj in queryset:
            AgencyFinanceService.reopen_month(obj.month)
            done += 1

        self.message_user(request, f"🔓 Re-opened {done} month(s).", level=messages.SUCCESS)