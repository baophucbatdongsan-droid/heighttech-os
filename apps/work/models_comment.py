from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.managers import TenantAllManager, TenantManager


class WorkComment(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, db_index=True)
    work_item = models.ForeignKey(
        "work.WorkItem",
        on_delete=models.CASCADE,
        related_name="comments",
        db_index=True,
    )

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="work_comments",
    )

    body = models.TextField(blank=True, default="")
    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        db_table = "work_comment"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["tenant", "work_item"], name="wc_t_wi_idx"),
            models.Index(fields=["tenant", "created_at"], name="wc_t_ct_idx"),
        ]

    def __str__(self) -> str:
        return f"Comment#{self.pk} item={self.work_item_id}"