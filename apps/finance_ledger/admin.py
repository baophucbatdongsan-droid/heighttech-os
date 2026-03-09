from django.contrib import admin

from apps.finance_ledger.models import LedgerEntry


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "tenant",
        "entry_type",
        "amount",
        "contract",
        "shop",
        "source_type",
        "created_at",
    )

    list_filter = ("tenant", "entry_type")

    search_fields = ("description", "source_type")