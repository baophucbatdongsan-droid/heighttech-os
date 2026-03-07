# apps/os/models.py
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.managers import TenantAllManager, TenantManager
from .models_action_log import OSActionLog

class OSNotification(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Mới"
        READ = "read", "Đã đọc"
        ARCHIVED = "archived", "Lưu trữ"

    class Severity(models.TextChoices):
        INFO = "info", "Thông tin"
        WARNING = "warning", "Cảnh báo"
        CRITICAL = "critical", "Nghiêm trọng"

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, db_index=True)
    company = models.ForeignKey("companies.Company", null=True, blank=True, on_delete=models.SET_NULL, db_index=True)
    shop = models.ForeignKey("shops.Shop", null=True, blank=True, on_delete=models.SET_NULL, db_index=True)

    # targeting
    target_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, db_index=True)
    target_role = models.CharField(max_length=30, blank=True, default="", db_index=True)  # founder/admin/operator/client/...

    # content (tiếng Việt)
    tieu_de = models.CharField(max_length=200, db_index=True)
    noi_dung = models.TextField(blank=True, default="")
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.INFO, db_index=True)

    # link entity
    entity_kind = models.CharField(max_length=50, blank=True, default="", db_index=True)  # workitem, shop, ...
    entity_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)

    meta = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW, db_index=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "status", "created_at"], name="osn_t_st_ct_idx"),
            models.Index(fields=["tenant", "target_user", "status"], name="osn_t_u_st_idx"),
            models.Index(fields=["tenant", "target_role", "status"], name="osn_t_r_st_idx"),
        ]

    def __str__(self) -> str:
        return f"OSNotification#{self.pk} {self.status} {self.tieu_de}"