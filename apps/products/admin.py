from django.contrib import admin

from apps.products.models import Product
from apps.products.models_stats import ProductDailyStat


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tenant",
        "shop",
        "sku",
        "name",
        "price",
        "cost",
        "stock",
        "status",
        "updated_at",
    )

    list_filter = (
        "tenant",
        "status",
    )

    search_fields = (
        "sku",
        "name",
    )

    autocomplete_fields = (
        "tenant",
        "shop",
        "company",
    )


@admin.register(ProductDailyStat)
class ProductDailyStatAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tenant",
        "shop",
        "product",
        "stat_date",
        "units_sold",
        "orders_count",
        "revenue",
        "ads_spend",
        "profit_estimate",
        "roas_estimate",
        "updated_at",
    )

    list_filter = (
        "tenant",
        "stat_date",
        "shop",
    )

    search_fields = (
        "product__sku",
        "product__name",
        "shop__name",
    )

    readonly_fields = ("created_at", "updated_at")

    autocomplete_fields = (
        "tenant",
        "company",
        "shop",
        "product",
    )