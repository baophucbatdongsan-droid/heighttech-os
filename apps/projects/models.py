# apps/projects/models.py
from __future__ import annotations

from typing import Set, Dict
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.core.managers import TenantManager, TenantAllManager
from apps.companies.models import Company
from apps.shops.models import Shop


# =====================================================
# ENUMS
# =====================================================

class ProjectStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    PAUSED = "paused", "Paused"
    DONE = "done", "Done"
    ARCHIVED = "archived", "Archived"


class ProjectType(models.TextChoices):
    SHOP_OPERATION = "shop_operation", "SHOP_OPERATION"
    BUILD_CHANNEL = "build_channel", "BUILD_CHANNEL"
    BOOKING = "booking", "BOOKING"


# =====================================================
# PROJECT (DOMAIN CORE)
# =====================================================

class Project(models.Model):

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

    name = models.CharField(max_length=255, db_index=True)

    type = models.CharField(
        max_length=30,
        choices=ProjectType.choices,
        default=ProjectType.SHOP_OPERATION,
        db_index=True,
    )

    status = models.CharField(
        max_length=20,
        choices=ProjectStatus.choices,
        default=ProjectStatus.DRAFT,
        db_index=True,
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_projects",
    )

    # ---------- OPS METRICS ----------
    progress_percent = models.PositiveSmallIntegerField(default=0, db_index=True)
    health_score = models.PositiveSmallIntegerField(default=100, db_index=True)
    last_activity_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # ---------- TIME ----------
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ---------- MANAGERS ----------
    objects = TenantManager()
    objects_all = TenantAllManager()

    # =====================================================
    # STATE MACHINE
    # =====================================================

    _ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
        ProjectStatus.DRAFT: {ProjectStatus.ACTIVE, ProjectStatus.ARCHIVED},
        ProjectStatus.ACTIVE: {ProjectStatus.PAUSED, ProjectStatus.DONE},
        ProjectStatus.PAUSED: {ProjectStatus.ACTIVE, ProjectStatus.ARCHIVED},
        ProjectStatus.DONE: {ProjectStatus.ARCHIVED},
        ProjectStatus.ARCHIVED: set(),
    }

    # =====================================================
    # CORE DOMAIN LOGIC
    # =====================================================

    def transition_to(self, new_status: str, *, actor=None, reason: str | None = None):

        if new_status == self.status:
            return

        if new_status not in ProjectStatus.values:
            raise ValidationError(f"Unknown status: {new_status}")

        allowed = self._ALLOWED_TRANSITIONS.get(self.status, set())

        if new_status not in allowed:
            raise ValidationError(
                f"Invalid transition: {self.status} → {new_status}"
            )

        # ----- side effects -----

        if self.status == ProjectStatus.DRAFT and new_status == ProjectStatus.ACTIVE:
            self.started_at = timezone.now()

        if new_status in (ProjectStatus.DONE, ProjectStatus.ARCHIVED):
            self.ended_at = timezone.now()

        self.status = new_status
        self.updated_at = timezone.now()

        self.save(update_fields=["status", "started_at", "ended_at", "updated_at"])

        # Hook future automation
        self._after_status_change(actor=actor, reason=reason)

    # =====================================================
    # PROTECTION RULES
    # =====================================================

    def clean(self):
        if self.status == ProjectStatus.ARCHIVED:
            raise ValidationError("Archived project cannot be modified.")

    def save(self, *args, **kwargs):
        if not self.tenant_id and self.company_id:
            self.tenant_id = self.company.tenant_id
        super().save(*args, **kwargs)

    # =====================================================
    # INTERNAL HOOK (future automation engine)
    # =====================================================

    def _after_status_change(self, *, actor=None, reason=None):
        """
        Reserved for:
        - Audit log
        - Notification
        - Automation trigger
        - Metric recalculation
        """
        self.last_activity_at = timezone.now()
        super().save(update_fields=["last_activity_at"])

    def __str__(self):
        return f"{self.name} [{self.status}]"


# =====================================================
# PROJECT SHOP LINK
# =====================================================

class ProjectShop(models.Model):

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

    role = models.CharField(
        max_length=30,
        default="operation",
        db_index=True,
    )

    status = models.CharField(
        max_length=20,
        default="active",
        db_index=True,
    )

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
            models.UniqueConstraint(
                fields=["tenant", "project", "shop"],
                name="uq_project_shop_unique"
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.tenant_id and self.project_id:
            self.tenant_id = self.project.tenant_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.project_id} - {self.shop_id}"