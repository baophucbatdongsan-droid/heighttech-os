# apps/projects/models.py
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.managers import TenantManager, TenantAllManager
from apps.companies.models import Company
from apps.shops.models import Shop


class Project(models.Model):
    """
    Project = Job (cấp Company).
    1 Company có nhiều Project.
    Project gom nhiều Shop theo role: OPERATION / BUILD_CHANNEL / BOOKING.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="projects",
        db_index=True,
    )

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="projects",
        db_index=True,
    )

    # ---------------- TYPE ----------------
    TYPE_SHOP_OPERATION = "shop_operation"
    TYPE_BUILD_CHANNEL = "build_channel"
    TYPE_BOOKING = "booking"

    TYPE_CHOICES = [
        (TYPE_SHOP_OPERATION, "SHOP_OPERATION"),
        (TYPE_BUILD_CHANNEL, "BUILD_CHANNEL"),
        (TYPE_BOOKING, "BOOKING"),
    ]

    # ---------------- STATUS ----------------
    STATUS_ACTIVE = "active"
    STATUS_PAUSED = "paused"
    STATUS_DONE = "done"
    STATUS_INACTIVE = "inactive"  # ✅ để match UI

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_PAUSED, "Paused"),
        (STATUS_DONE, "Done"),
        (STATUS_INACTIVE, "Inactive"),
    ]

    # ---------------- CORE ----------------
    name = models.CharField(max_length=255, db_index=True)
    type = models.CharField(max_length=30, choices=TYPE_CHOICES, default=TYPE_SHOP_OPERATION, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_projects",
    )

    # ---------------- OPS METRICS ----------------
    # 0..100 (service/cron/signal sẽ update)
    progress_percent = models.PositiveSmallIntegerField(default=0, db_index=True)
    health_score = models.PositiveSmallIntegerField(default=100, db_index=True)
    last_activity_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # ---------------- TIME ----------------
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ---------------- MANAGERS ----------------
    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["tenant", "status"], name="idx_project_tenant_status"),
            models.Index(fields=["tenant", "type"], name="idx_project_tenant_type"),
            models.Index(fields=["tenant", "company"], name="idx_project_tenant_company"),
        ]

    def save(self, *args, **kwargs):
        if not self.tenant_id and self.company_id:
            self.tenant_id = self.company.tenant_id
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} ({self.type})"


class ProjectShop(models.Model):
    """
    Link Shop vào Project + role.
    1 Project có nhiều Shop.
    1 Shop có thể thuộc nhiều Project.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="project_shops",
        db_index=True,
    )

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="project_shops",
        db_index=True,
    )

    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name="project_links",
        db_index=True,
    )

    # ---------------- ROLE ----------------
    ROLE_OPERATION = "operation"
    ROLE_BUILD = "build_channel"
    ROLE_BOOKING = "booking"

    ROLE_CHOICES = [
        (ROLE_OPERATION, "Shop Operation"),
        (ROLE_BUILD, "Build Channel"),
        (ROLE_BOOKING, "Booking"),
    ]

    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default=ROLE_OPERATION, db_index=True)

    # ---------------- STATUS ----------------
    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"
    STATUS_PAUSED = "paused"
    STATUS_DONE = "done"

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_INACTIVE, "Inactive"),
        (STATUS_PAUSED, "Paused"),
        (STATUS_DONE, "Done"),
    ]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True)

    assigned_pm = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="managed_project_shops",
    )

    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "project", "shop"], name="uq_project_shop_unique"),
        ]
        indexes = [
            models.Index(fields=["tenant", "project"], name="idx_projectshop_tenant_project"),
            models.Index(fields=["tenant", "shop"], name="idx_projectshop_tenant_shop"),
        ]

    def save(self, *args, **kwargs):
        if not self.tenant_id and self.project_id:
            self.tenant_id = self.project.tenant_id
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.project_id} - {self.shop_id}"