# apps/tenants/models.py
from __future__ import annotations

from django.db import models
from django.utils import timezone


# ==========================================================
# AGENCY
# ==========================================================
class Agency(models.Model):
    name = models.CharField(max_length=255, verbose_name="Tên Agency")
    is_active = models.BooleanField(default=True, verbose_name="Hoạt động")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Agency"
        verbose_name_plural = "Danh sách Agency"
        ordering = ["-id"]

    def __str__(self) -> str:
        return self.name


# ==========================================================
# TENANT (Core SaaS Customer)
# ==========================================================
class Tenant(models.Model):
    """
    Tenant = 1 khách hàng / 1 workspace SaaS
    """

    # ---------------- PLAN ----------------
    PLAN_BASIC = "basic"
    PLAN_PRO = "pro"
    PLAN_ENT = "enterprise"

    PLAN_CHOICES = [
        (PLAN_BASIC, "Basic"),
        (PLAN_PRO, "Pro"),
        (PLAN_ENT, "Enterprise"),
    ]

    # ---------------- STATUS ----------------
    class Status(models.TextChoices):
        TRIAL = "trial", "Trial"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    # Backward-compatible constants (để code cũ không chết)
    STATUS_TRIAL = Status.TRIAL
    STATUS_ACTIVE = Status.ACTIVE
    STATUS_SUSPENDED = Status.SUSPENDED

    # ---------------- RELATIONS ----------------
    agency = models.ForeignKey(
        "tenants.Agency",
        on_delete=models.CASCADE,
        related_name="tenants",
        null=True,
        blank=True,
        verbose_name="Agency quản lý",
    )

    # ---------------- CORE INFO ----------------
    name = models.CharField(max_length=255, blank=True, default="")
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default=PLAN_BASIC)

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )

    # Nếu bạn muốn "soft disable" tenant hoàn toàn (không tính billing/không cho login…)
    is_active = models.BooleanField(default=True)

    # ---------------- FEATURE CONTROL ----------------
    # Feature flags dạng JSON: {"rate_limit": true, "billing": true, ...}
    feature_flags = models.JSONField(default=dict, blank=True)

    # Optional override rate limit per tenant
    req_per_min_override = models.PositiveIntegerField(null=True, blank=True)

    # Khi bị suspended thì ghi dấu thời điểm
    suspended_at = models.DateTimeField(null=True, blank=True)

    # ---------------- TIMESTAMPS ----------------
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tenant"
        verbose_name_plural = "Danh sách Tenant"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["plan"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        return self.name or f"Tenant#{self.pk}"


# ==========================================================
# TENANT DOMAIN (Host → Tenant Mapping)
# ==========================================================
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

    # lưu host sạch (không kèm port)
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
            models.Index(fields=["tenant", "is_active"]),
            models.Index(fields=["domain", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.domain} -> Tenant#{self.tenant_id}"


# ==========================================================
# OPTIONAL: Subscription extension (nếu có)
# ==========================================================
try:
    from .models_subscription import *  # noqa
except Exception:
    pass