# apps/os/models_action_log.py
from __future__ import annotations

from django.db import models
from django.utils import timezone

from apps.core.managers import TenantAllManager, TenantManager


class OSActionLog(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, db_index=True)

    action_type = models.CharField(max_length=120, db_index=True)
    dedupe_key = models.CharField(max_length=180, db_index=True, unique=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW, db_index=True)
    result = models.JSONField(default=dict, blank=True)
    last_error = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    objects = TenantManager()
    objects_all = TenantAllManager()

    def __str__(self) -> str:
        return f"OSActionLog#{self.pk} {self.action_type} {self.status}"