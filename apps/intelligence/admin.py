# apps/intelligence/admin.py
from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html

from apps.intelligence.models import ShopHealthSnapshot


@admin.register(ShopHealthSnapshot)
class ShopHealthSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "month",
        "shop",
        "company",
        "brand",
        "risk_badge",
        "score",
        "revenue_3m",
        "net_3m",
        "margin_3m",
        "growth_last_mom",
        "calculated_at",
    )
    list_filter = ("month", "risk", "company")
    search_fields = ("shop__name", "company__name", "brand__name")
    date_hierarchy = "month"
    ordering = ("-month", "-score")
    readonly_fields = ("created_at", "updated_at", "calculated_at")

    def risk_badge(self, obj: ShopHealthSnapshot):
        color = "#2ecc71"
        if obj.risk == "MED":
            color = "#f39c12"
        elif obj.risk == "HIGH":
            color = "#e74c3c"
        return format_html(
            '<span style="padding:2px 8px;border-radius:999px;background:{};color:white;font-weight:700;">{}</span>',
            color,
            obj.risk,
        )

    risk_badge.short_description = "Risk"