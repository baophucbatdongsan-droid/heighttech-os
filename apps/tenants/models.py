# apps/tenants/models.py
from __future__ import annotations

from django.db import models
from django.utils import timezone


class Agency(models.Model):
    name = models.CharField(max_length=255, verbose_name="Tên Agency")
    is_active = models.BooleanField(default=True, verbose_name="Hoạt động")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Agency"
        verbose_name_plural = "Danh sách Agency"
        ordering = ["-id"]

    def __str__(self):
        return self.name


class Tenant(models.Model):
    """
    Tenant = 1 khách hàng / 1 workspace.
    """
    agency = models.ForeignKey(
        "tenants.Agency",
        on_delete=models.CASCADE,
        related_name="tenants",
        null=True,
        blank=True,
        verbose_name="Agency quản lý",
    )

    name = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tenant"
        verbose_name_plural = "Danh sách Tenant"
        ordering = ["-id"]

    def __str__(self):
        return self.name or f"Tenant#{self.pk}"


class TenantDomain(models.Model):
    """
    Map domain/host -> tenant
    Ví dụ:
    - localhost
    - 127.0.0.1
    - heighttech.com
    - shop1.heighttech.com
    """
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="domains",
    )

    # lưu host sạch: không port
    domain = models.CharField(max_length=255, unique=True, db_index=True)

    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tenant Domain"
        verbose_name_plural = "Tenant Domains"
        ordering = ["domain"]
        indexes = [
            models.Index(fields=["tenant", "is_active"], name="idx_td_tenant_active"),
        ]

    def __str__(self):
        return f"{self.domain} -> Tenant#{self.tenant_id}"


# ✅ nếu bạn có models_subscription.py thì keep
from .models_subscription import *  # noqa