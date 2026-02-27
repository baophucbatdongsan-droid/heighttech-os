# apps/companies/models.py
from __future__ import annotations

from django.db import models
from django.utils import timezone

from apps.core.tenant_managers import TenantManager


class Company(models.Model):
    # =========================
    # MULTI TENANT
    # =========================
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="companies",
        db_index=True,
        verbose_name="Tenant",
    )

    # =========================
    # AGENCY (OPTIONAL)
    # =========================
    agency = models.ForeignKey(
        "tenants.Agency",
        on_delete=models.SET_NULL,
        related_name="companies",
        null=True,
        blank=True,
        verbose_name="Agency quản lý",
    )

    # =========================
    # BASIC INFO
    # =========================
    name = models.CharField(max_length=255, db_index=True, verbose_name="Tên Company")

    max_clients = models.IntegerField(default=5, verbose_name="Số client tối đa")
    months_active = models.IntegerField(default=0, verbose_name="Số tháng hoạt động")

    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Đang hoạt động")

    # =========================
    # TIMESTAMPS
    # =========================
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Ngày tạo")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Cập nhật")

    # =========================
    # MANAGERS
    # =========================
    objects = TenantManager()        # scoped
    objects_all = models.Manager()   # unscoped fallback

    class Meta:
        verbose_name = "Company"
        verbose_name_plural = "Companies"
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uq_company_tenant_name"),
        ]
        indexes = [
            models.Index(fields=["tenant"], name="idx_company_tenant"),
            models.Index(fields=["is_active"], name="idx_company_active"),
            models.Index(fields=["tenant", "is_active"], name="idx_company_tenant_active"),
        ]

    def __str__(self) -> str:
        # tránh crash nếu tenant chưa load
        tenant_name = getattr(self.tenant, "name", f"tenant#{self.tenant_id}")
        return f"{self.name} ({tenant_name})"