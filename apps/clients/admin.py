from django.contrib import admin
from .models import Client
from apps.core.base_admin import BaseCompanyAdmin


@admin.register(Client)
class ClientAdmin(BaseCompanyAdmin):
    list_display = (
        "brand_name",
        "company",
        "account_manager",
        "operator",
        "fixed_fee",
        "percent_fee",
    )

    list_filter = ("company",)
    search_fields = ("brand_name",)

    ordering = ("brand_name",)