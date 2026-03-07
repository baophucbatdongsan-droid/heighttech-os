# apps/core/models.py
from __future__ import annotations

from typing import Optional

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.tenant_context import get_current_tenant


# ==========================================================
# BASE MODELS
# ==========================================================

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Tạo lúc")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Cập nhật")

    class Meta:
        abstract = True


class TenantStampedModel(TimeStampedModel):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        db_index=True,
        verbose_name="Tenant",
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Hoạt động")

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["tenant"]),
            models.Index(fields=["tenant", "is_active"]),
        ]

    def _infer_tenant_from_context(self):
        return get_current_tenant()

    def save(self, *args, **kwargs):
        if not getattr(self, "tenant_id", None):
            t = self._infer_tenant_from_context()
            if t is not None:
                self.tenant = t
        super().save(*args, **kwargs)


class TenantOwnedModel(TenantStampedModel):
    owner_field: str = ""

    class Meta:
        abstract = True

    def resolve_tenant_from_owner(self) -> Optional[models.Model]:
        if not self.owner_field:
            return None

        owner = getattr(self, self.owner_field, None)
        if owner is None:
            return None

        if hasattr(owner, "tenant_id") and getattr(owner, "tenant_id", None):
            return getattr(owner, "tenant", None)

        return None

    def save(self, *args, **kwargs):
        if not getattr(self, "tenant_id", None):
            t = self.resolve_tenant_from_owner()
            if t is not None:
                self.tenant = t
        super().save(*args, **kwargs)


# ==========================================================
# AUDIT LOG (FINAL HARDENED VERSION)
# ==========================================================

class AuditLog(models.Model):
    """
    Enterprise Audit Log
    - Full request tracing
    - JSON before/after
    - Correlation IDs
    - Hardened for SaaS OS
    """

    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_DELETE = "delete"
    ACTION_BULK_UPDATE = "bulk_update"
    ACTION_EXPORT_CSV = "export_csv"

    ACTION_CHOICES = [
        (ACTION_CREATE, "Tạo mới"),
        (ACTION_UPDATE, "Cập nhật"),
        (ACTION_DELETE, "Xoá"),
        (ACTION_BULK_UPDATE, "Cập nhật hàng loạt"),
        (ACTION_EXPORT_CSV, "Xuất CSV"),
    ]

    tenant = models.ForeignKey(
        "tenants.Tenant",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        db_index=True,
        verbose_name="Tenant",
    )

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        verbose_name="Người thực hiện",
    )

    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        db_index=True,
        verbose_name="Hành động",
    )

    app_label = models.CharField(max_length=100, db_index=True, verbose_name="App")
    model_name = models.CharField(max_length=100, db_index=True, verbose_name="Model")
    object_pk = models.CharField(max_length=64, db_index=True, verbose_name="ID đối tượng")

    # Correlation
    request_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    trace_id = models.CharField(max_length=128, blank=True, default="", db_index=True)

    # Request meta
    path = models.CharField(max_length=255, blank=True, default="")
    method = models.CharField(max_length=16, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    referer = models.TextField(null=True, blank=True)

    # Data
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    changed_fields = models.JSONField(default=list, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["app_label", "model_name"], name="idx_audit_model"),
            models.Index(fields=["object_pk"], name="idx_audit_objectpk"),
            models.Index(fields=["tenant", "created_at"], name="idx_audit_tenant_time"),
            models.Index(fields=["request_id", "created_at"], name="idx_audit_req_time"),
        ]

    # ==========================================================
    # 🔥 CRITICAL HARDENING FOR TEST + STABILITY
    # ==========================================================

    def save(self, *args, **kwargs):
        """
        1. Nếu AUDIT_ENABLED=False (test mode) => NO-OP
        2. Auto-fill tenant nếu thiếu
        3. Never crash system
        """

        # 🔥 Absolute disable during tests
        if not getattr(settings, "AUDIT_ENABLED", True):
            return

        try:
            # Auto infer tenant if missing
            if not self.tenant_id:
                t = get_current_tenant()
                if t:
                    self.tenant = t

            super().save(*args, **kwargs)

        except Exception:
            # Audit MUST NEVER break business logic
            return

    def __str__(self) -> str:
        return (
            f"{self.created_at:%Y-%m-%d %H:%M} "
            f"{self.action} "
            f"{self.app_label}.{self.model_name}#{self.object_pk}"
        )