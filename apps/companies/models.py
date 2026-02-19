# apps/companies/models.py
from __future__ import annotations

from django.db import models
from django.utils import timezone

from apps.core.tenant_managers import TenantManager


class Company(models.Model):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="companies",
        db_index=True,
    )

    agency = models.ForeignKey(
        "tenants.Agency",
        on_delete=models.CASCADE,
        related_name="companies",
        null=True,
        blank=True,
        verbose_name="Agency quản lý",
    )

    name = models.CharField(max_length=255)
    max_clients = models.IntegerField(default=5)
    months_active = models.IntegerField(default=0)

    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    # ✅ managers
    objects = TenantManager()
    objects_all = models.Manager()  # unscoped fallback

    class Meta:
        ordering = ["-id"]
        unique_together = ("tenant", "name")
        indexes = [
            models.Index(fields=["tenant"], name="idx_company_tenant"),
            models.Index(fields=["is_active"], name="idx_company_active"),
        ]

    def __str__(self):
        return self.name
    # =============================
    # BASIC INFO
    # =============================
    name = models.CharField(max_length=255, verbose_name="Tên Company")

    max_clients = models.IntegerField(
        default=5,
        verbose_name="Số client tối đa"
    )

    months_active = models.IntegerField(
        default=0,
        verbose_name="Số tháng hoạt động"
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Đang hoạt động"
    )

    # =============================
    # AGENCY (OPTIONAL – nội bộ)
    # =============================
    agency = models.ForeignKey(
        "tenants.Agency",
        on_delete=models.SET_NULL,
        related_name="companies",
        null=True,
        blank=True,
        verbose_name="Agency quản lý"
    )

    # =============================
    # TIMESTAMPS
    # =============================
    created_at = models.DateTimeField(
        default=timezone.now,
        verbose_name="Ngày tạo"
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Cập nhật"
    )

    # =============================
    # META
    # =============================
    class Meta:
        verbose_name = "Company"
        verbose_name_plural = "Companies"
        ordering = ["-id"]
        unique_together = ("tenant", "name")  # 🔥 cực quan trọng
        indexes = [
            models.Index(fields=["tenant"], name="idx_company_tenant"),
            models.Index(fields=["is_active"], name="idx_company_active"),
        ]

    # =============================
    # STR
    # =============================
    def __str__(self):
        return f"{self.name} ({self.tenant.name})"