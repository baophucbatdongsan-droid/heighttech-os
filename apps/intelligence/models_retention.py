from __future__ import annotations

from django.db import models
from django.utils import timezone


class ShopRetentionState(models.Model):
    """
    Snapshot giữ chân shop theo tháng.
    Tách khỏi health để scale độc lập.
    """

    month = models.DateField()

    shop_id = models.IntegerField(db_index=True)
    shop_name = models.CharField(max_length=255, blank=True, default="")
    company_name = models.CharField(max_length=255, blank=True, default="")

    retention_score = models.IntegerField(default=0)  # 0–100
    escalation_level = models.IntegerField(default=0)  # 0/1/2/3
    badge = models.CharField(max_length=32, default="STABLE")

    consecutive_high_risk = models.IntegerField(default=0)
    consecutive_loss = models.IntegerField(default=0)

    auto_flag = models.BooleanField(default=False)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-month", "-retention_score"]
        unique_together = ("month", "shop_id")
        indexes = [
            models.Index(fields=["month"]),
            models.Index(fields=["escalation_level"]),
            models.Index(fields=["retention_score"]),
        ]

    def __str__(self):
        return f"{self.month} | {self.shop_name} | score={self.retention_score} | L{self.escalation_level}"