from __future__ import annotations

from django.contrib import admin

from .models import Channel, ChannelAccount, ChannelShopLink


@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "company", "type", "name", "is_active", "created_at")
    list_filter = ("type", "is_active", "company")
    search_fields = ("name",)


@admin.register(ChannelAccount)
class ChannelAccountAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "channel", "account_name", "external_id", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("account_name", "external_id")


@admin.register(ChannelShopLink)
class ChannelShopLinkAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "channel", "shop", "created_at")
    list_filter = ("channel",)