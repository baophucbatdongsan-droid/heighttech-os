from __future__ import annotations

from django.contrib import admin, messages

from apps.contracts.models import (
    Contract,
    ContractBookingItem,
    ContractMilestone,
    ContractPayment,
    ContractShop,
)

# NẾU FILE THẬT CỦA ANH LÀ services.py THÌ GIỮ NGUYÊN DÒNG DƯỚI
from apps.contracts.services import rebuild_contract_schedule

# NẾU FILE THẬT CỦA ANH LÀ service.py THÌ DÙNG DÒNG NÀY THAY THẾ:
# from apps.contracts.service import rebuild_contract_schedule


class ContractShopInline(admin.TabularInline):
    model = ContractShop
    extra = 0
    autocomplete_fields = ("shop",)


class ContractMilestoneInline(admin.TabularInline):
    model = ContractMilestone
    extra = 0
    autocomplete_fields = ("company", "shop")
    fields = ("title", "kind", "status", "due_at", "done_at", "sort_order")


class ContractPaymentInline(admin.TabularInline):
    model = ContractPayment
    extra = 0
    fields = (
        "title",
        "amount",
        "vat_percent",
        "vat_amount",
        "total_amount",
        "due_at",
        "paid_amount",
        "paid_at",
        "status",
    )
    readonly_fields = ("vat_amount", "total_amount")


class ContractBookingItemInline(admin.TabularInline):
    model = ContractBookingItem
    extra = 0
    autocomplete_fields = ("company", "shop")
    fields = (
        "koc_name",
        "booking_type",
        "unit_price",
        "commission_percent",
        "brand_amount",
        "payout_amount",
        "air_date",
        "video_link",
        "payout_due_at",
        "payout_status",
    )


@admin.action(description="Tạo lại milestone/payment tự động")
def action_rebuild_schedule(modeladmin, request, queryset):
    ok = 0
    fail = 0

    for obj in queryset:
        try:
            rebuild_contract_schedule(obj)
            ok += 1
        except Exception as e:
            fail += 1
            modeladmin.message_user(
                request,
                f"Hợp đồng #{obj.id} tạo lịch lỗi: {e}",
                level=messages.WARNING,
            )

    if ok:
        modeladmin.message_user(
            request,
            f"Đã tạo lại lịch tự động cho {ok} hợp đồng.",
            level=messages.SUCCESS,
        )
    if fail:
        modeladmin.message_user(
            request,
            f"Có {fail} hợp đồng tạo lịch thất bại.",
            level=messages.WARNING,
        )


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tenant",
        "code",
        "name",
        "contract_type",
        "status",
        "company",
        "start_date",
        "end_date",
        "total_value",
        "vat_percent",
        "updated_at",
    )
    list_filter = ("tenant", "contract_type", "status")
    search_fields = ("code", "name", "partner_name", "note")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("company",)
    actions = [action_rebuild_schedule]
    inlines = [
        ContractShopInline,
        ContractMilestoneInline,
        ContractPaymentInline,
        ContractBookingItemInline,
    ]


@admin.register(ContractShop)
class ContractShopAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "contract", "shop", "created_at")
    list_filter = ("tenant",)
    search_fields = ("contract__code", "contract__name", "shop__name")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("contract", "shop")


@admin.register(ContractMilestone)
class ContractMilestoneAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "contract", "title", "kind", "status", "shop", "due_at", "done_at")
    list_filter = ("tenant", "kind", "status")
    search_fields = ("title", "description", "contract__code", "contract__name")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("contract", "company", "shop")


@admin.register(ContractPayment)
class ContractPaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tenant",
        "contract",
        "title",
        "amount",
        "vat_percent",
        "vat_amount",
        "total_amount",
        "due_at",
        "paid_amount",
        "paid_at",
        "status",
    )
    list_filter = ("tenant", "status")
    search_fields = ("title", "contract__code", "contract__name", "note")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("contract", "milestone")


@admin.register(ContractBookingItem)
class ContractBookingItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tenant",
        "contract",
        "koc_name",
        "booking_type",
        "shop",
        "air_date",
        "video_link",
        "payout_amount",
        "payout_due_at",
        "payout_status",
    )
    list_filter = ("tenant", "booking_type", "payout_status")
    search_fields = ("koc_name", "koc_channel_name", "contract__code", "contract__name", "video_link")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("contract", "company", "shop")