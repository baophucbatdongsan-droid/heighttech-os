# apps/events/models.py
from __future__ import annotations

from django.db import models
from django.utils import timezone

from apps.core.managers import TenantAllManager, TenantManager


class OutboxEvent(models.Model):
    """
    DB-backed outbox (at-least-once).
    Worker sẽ pull theo status=NEW và lock row.
    """

    class Status(models.TextChoices):
        NEW = "new", "New"
        PROCESSING = "processing", "Processing"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, db_index=True)
    company = models.ForeignKey("companies.Company", null=True, blank=True, on_delete=models.SET_NULL, db_index=True)
    shop = models.ForeignKey("shops.Shop", null=True, blank=True, on_delete=models.SET_NULL, db_index=True)

    actor_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)

    name = models.CharField(max_length=120, db_index=True)         # e.g. work.item.updated
    version = models.PositiveIntegerField(default=1, db_index=True)

    dedupe_key = models.CharField(max_length=180, blank=True, default="", db_index=True)

    payload = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW, db_index=True)
    attempts = models.PositiveIntegerField(default=0)

    available_at = models.DateTimeField(default=timezone.now, db_index=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        indexes = [
            models.Index(fields=["status", "available_at", "id"], name="obx_st_av_id_idx"),
            models.Index(fields=["tenant", "name", "created_at"], name="obx_t_nm_ct_idx"),
            models.Index(fields=["dedupe_key"], name="obx_dedupe_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["dedupe_key"],
                name="uq_outbox_dedupe_key",
                condition=~models.Q(dedupe_key=""),
            )
        ]

    def __str__(self) -> str:
        return f"OutboxEvent#{self.pk} {self.name} {self.status}"