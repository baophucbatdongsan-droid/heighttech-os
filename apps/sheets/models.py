from __future__ import annotations

from django.conf import settings
from django.db import models


class Sheet(models.Model):
    MODULE_CUSTOM = "custom"
    MODULE_WORK = "work"
    MODULE_CONTRACT = "contract"
    MODULE_CONTENT = "content"
    MODULE_FINANCE = "finance"
    MODULE_BOOKING = "booking"

    MODULE_CHOICES = (
        (MODULE_CUSTOM, "Custom"),
        (MODULE_WORK, "Work"),
        (MODULE_CONTRACT, "Contract"),
        (MODULE_CONTENT, "Content"),
        (MODULE_FINANCE, "Finance"),
        (MODULE_BOOKING, "Booking"),
    )

    tenant_id = models.BigIntegerField(db_index=True)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, blank=True, default="")
    module_code = models.CharField(
        max_length=50,
        choices=MODULE_CHOICES,
        default=MODULE_CUSTOM,
        db_index=True,
    )

    linked_target_type = models.CharField(max_length=50, blank=True, default="", db_index=True)
    linked_target_id = models.BigIntegerField(null=True, blank=True, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sheets_created",
    )

    is_deleted = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sheets_sheet"
        ordering = ("-id",)
        indexes = [
            models.Index(fields=["tenant_id", "module_code"]),
            models.Index(fields=["tenant_id", "linked_target_type", "linked_target_id"]),
        ]

    def __str__(self) -> str:
        return self.name or f"Sheet #{self.pk}"


class SheetColumn(models.Model):
    DATA_TEXT = "text"
    DATA_NUMBER = "number"
    DATA_DATE = "date"
    DATA_SELECT = "select"
    DATA_IMAGE = "image"

    DATA_TYPE_CHOICES = (
        (DATA_TEXT, "Text"),
        (DATA_NUMBER, "Number"),
        (DATA_DATE, "Date"),
        (DATA_SELECT, "Select"),
        (DATA_IMAGE, "Image"),
    )

    sheet = models.ForeignKey(
        Sheet,
        on_delete=models.CASCADE,
        related_name="columns",
    )
    name = models.CharField(max_length=255)
    key = models.SlugField(max_length=255, blank=True, default="")
    data_type = models.CharField(
        max_length=20,
        choices=DATA_TYPE_CHOICES,
        default=DATA_TEXT,
    )
    position = models.IntegerField(default=0, db_index=True)
    is_required = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sheets_sheet_column"
        ordering = ("position", "id")
        unique_together = (("sheet", "position"),)

    def __str__(self) -> str:
        return self.name or f"Column #{self.pk}"


class SheetRow(models.Model):
    sheet = models.ForeignKey(
        Sheet,
        on_delete=models.CASCADE,
        related_name="rows",
    )
    position = models.IntegerField(default=0, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sheet_rows_created",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sheets_sheet_row"
        ordering = ("position", "id")
        unique_together = (("sheet", "position"),)

    def __str__(self) -> str:
        return f"Row #{self.pk} / Sheet #{self.sheet_id}"


class SheetCell(models.Model):
    row = models.ForeignKey(
        SheetRow,
        on_delete=models.CASCADE,
        related_name="cells",
    )
    column = models.ForeignKey(
        SheetColumn,
        on_delete=models.CASCADE,
        related_name="cells",
    )
    value_text = models.TextField(blank=True, default="")

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sheet_cells_updated",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sheets_sheet_cell"
        unique_together = (("row", "column"),)

    def __str__(self) -> str:
        return f"Cell r{self.row_id} c{self.column_id}"