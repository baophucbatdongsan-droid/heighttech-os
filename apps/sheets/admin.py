from __future__ import annotations

from django.contrib import admin

from apps.sheets.models import Sheet, SheetCell, SheetColumn, SheetRow


@admin.register(Sheet)
class SheetAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tenant_id",
        "name",
        "module_code",
        "linked_target_type",
        "linked_target_id",
        "created_by",
        "created_at",
    )
    list_filter = ("module_code", "linked_target_type", "tenant_id", "is_deleted")
    search_fields = ("name", "slug")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("created_by",)


@admin.register(SheetColumn)
class SheetColumnAdmin(admin.ModelAdmin):
    list_display = ("id", "sheet", "name", "data_type", "position", "is_required")
    list_filter = ("data_type",)
    search_fields = ("name", "key", "sheet__name")
    autocomplete_fields = ("sheet",)


@admin.register(SheetRow)
class SheetRowAdmin(admin.ModelAdmin):
    list_display = ("id", "sheet", "position", "created_by", "created_at")
    search_fields = ("id", "sheet__name")
    autocomplete_fields = ("sheet", "created_by")
    readonly_fields = ("created_at", "updated_at")


@admin.register(SheetCell)
class SheetCellAdmin(admin.ModelAdmin):
    list_display = ("id", "row", "column", "updated_by", "updated_at")
    search_fields = ("value_text", "row__sheet__name", "column__name")
    autocomplete_fields = ("row", "column", "updated_by")
    readonly_fields = ("updated_at",)