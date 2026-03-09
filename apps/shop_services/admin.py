from __future__ import annotations

from django.contrib import admin

from apps.shop_services.models import ShopServiceSubscription


@admin.register(ShopServiceSubscription)
class ShopServiceSubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tenant",
        "shop",
        "service_code",
        "status",
        "company",
        "contract",
        "owner",
        "start_date",
        "end_date",
        "updated_at",
    )
    list_filter = (
        "tenant",
        "service_code",
        "status",
    )
    search_fields = (
        "shop__name",
        "service_name",
        "note",
        "contract__code",
        "contract__name",
    )
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("company", "shop", "contract", "owner")