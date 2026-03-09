from __future__ import annotations

from django.db import models
from django.utils import timezone

from apps.core.managers import TenantManager, TenantAllManager


class LedgerEntry(models.Model):

    class EntryType(models.TextChoices):
        REVENUE = "revenue", "Doanh thu"
        EXPENSE = "expense", "Chi phí"

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        db_index=True,
    )

    contract = models.ForeignKey(
        "contracts.Contract",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_index=True,
    )

    shop = models.ForeignKey(
        "shops.Shop",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_index=True,
    )

    entry_type = models.CharField(
        max_length=20,
        choices=EntryType.choices,
        db_index=True,
    )

    amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0,
    )

    source_type = models.CharField(
        max_length=50,
        blank=True,
        default="",
        db_index=True,
    )

    source_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        db_index=True,
    )

    description = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["tenant", "entry_type"], name="ledger_t_tp_idx"),
            models.Index(fields=["tenant", "contract"], name="ledger_t_ct_idx"),
        ]

    def __str__(self):
        return f"{self.entry_type} {self.amount}"