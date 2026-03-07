from __future__ import annotations

from django.db import models
from django.utils import timezone

from apps.core.managers import TenantAllManager, TenantManager


class Notification(models.Model):
    """
    Thông báo in-app (beta).
    Nguồn: OutboxEvent (work.*, os.*) -> handler -> tạo Notification.
    """

    class Level(models.TextChoices):
        INFO = "info", "Thông tin"
        WARNING = "warning", "Cảnh báo"
        CRITICAL = "critical", "Khẩn cấp"

    class Status(models.TextChoices):
        UNREAD = "unread", "Chưa đọc"
        READ = "read", "Đã đọc"
        ARCHIVED = "archived", "Lưu trữ"

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, db_index=True)
    company = models.ForeignKey("companies.Company", null=True, blank=True, on_delete=models.SET_NULL, db_index=True)
    shop = models.ForeignKey("shops.Shop", null=True, blank=True, on_delete=models.SET_NULL, db_index=True)

    actor_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)     # ai gây ra
    user_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)      # ai nhận (nullable = broadcast)

    level = models.CharField(max_length=20, choices=Level.choices, default=Level.INFO, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNREAD, db_index=True)

    tieu_de = models.CharField(max_length=255, blank=True, default="")
    noi_dung = models.TextField(blank=True, default="")

    # link tới đối tượng (workitem/project/...)
    doi_tuong_loai = models.CharField(max_length=50, blank=True, default="", db_index=True)
    doi_tuong_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)

    # idempotent (dedupe theo event)
    dedupe_key = models.CharField(max_length=180, blank=True, default="", db_index=True)

    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["tenant", "status", "created_at"], name="ntf_t_st_ct_idx"),
            models.Index(fields=["tenant", "shop", "status", "created_at"], name="ntf_t_sh_st_ct_idx"),
            models.Index(fields=["tenant", "user_id", "status", "created_at"], name="ntf_t_u_st_ct_idx"),
            models.Index(fields=["dedupe_key"], name="ntf_dedupe_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["dedupe_key"],
                name="uq_notification_dedupe_key",
                condition=~models.Q(dedupe_key=""),
            )
        ]

    def mark_read(self):
        if self.status != self.Status.READ:
            self.status = self.Status.READ
            self.read_at = timezone.now()
            self.save(update_fields=["status", "read_at"])