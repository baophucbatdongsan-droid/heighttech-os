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
    """
    Base: created_at / updated_at
    Dùng cho model nào không cần tenant.
    """
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Tạo lúc")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Cập nhật")

    class Meta:
        abstract = True


class TenantStampedModel(TimeStampedModel):
    """
    Base chuẩn cho SaaS multi-tenant.
    - tenant: scope data
    - is_active: soft deactivate
    - auto gán tenant từ request context (CurrentRequestMiddleware)
    """
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        db_index=True,
        verbose_name="Tenant",
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Hoạt động")

    class Meta:
        abstract = True
        # ⚠️ Không đặt name cố định trong abstract base để tránh đụng index name
        indexes = [
            models.Index(fields=["tenant"]),
            models.Index(fields=["tenant", "is_active"]),
        ]

    def _infer_tenant_from_context(self):
        """
        Lấy tenant từ contextvars (middleware set).
        """
        return get_current_tenant()

    def save(self, *args, **kwargs):
        if not getattr(self, "tenant_id", None):
            t = self._infer_tenant_from_context()
            if t is not None:
                self.tenant = t
        super().save(*args, **kwargs)


class TenantOwnedModel(TenantStampedModel):
    """
    Optional: dùng cho model có owner FK để tự sync tenant.

    Ví dụ:
      - Brand: owner_field = "company"
      - Shop: owner_field = "brand" (brand -> company -> tenant)
      - MonthlyPerformance: owner_field = "shop" (shop -> brand -> company -> tenant)

    Override `owner_field` và `resolve_tenant_from_owner()` nếu cần.
    """
    owner_field: str = ""

    class Meta:
        abstract = True

    def resolve_tenant_from_owner(self) -> Optional[models.Model]:
        """
        Default strategy:
        - Nếu owner có field tenant => lấy luôn
        - Nếu owner không có tenant nhưng có chain khác => override ở model con.
        """
        if not self.owner_field:
            return None

        owner = getattr(self, self.owner_field, None)
        if owner is None:
            return None

        # direct tenant
        if hasattr(owner, "tenant_id") and getattr(owner, "tenant_id", None):
            return getattr(owner, "tenant", None)

        return None

    def save(self, *args, **kwargs):
        # ưu tiên sync từ owner trước
        if not getattr(self, "tenant_id", None):
            t = self.resolve_tenant_from_owner()
            if t is not None:
                self.tenant = t

        # fallback từ context (TenantStampedModel.save sẽ lo)
        super().save(*args, **kwargs)


# ==========================================================
# AUDIT LOG
# ==========================================================

class AuditLog(models.Model):
    """
    Log thay đổi dữ liệu quan trọng (MonthlyPerformance, Shop, Brand, Company...).
    Ghi theo request/user hiện tại (thread-local middleware).
    """

    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_DELETE = "delete"

    ACTION_CHOICES = [
        (ACTION_CREATE, "Create"),
        (ACTION_UPDATE, "Update"),
        (ACTION_DELETE, "Delete"),
    ]

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        verbose_name="Actor",
    )

    action = models.CharField(max_length=20, choices=ACTION_CHOICES)

    # model identity
    app_label = models.CharField(max_length=100)
    model_name = models.CharField(max_length=100)
    object_pk = models.CharField(max_length=64)

    # tenant scope (optional)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        db_index=True,
        verbose_name="Tenant",
    )

    # request meta
    path = models.CharField(max_length=255, blank=True, default="")
    method = models.CharField(max_length=16, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    referer = models.TextField(null=True, blank=True)

    # snapshots
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Audit log"
        verbose_name_plural = "Audit logs"
        indexes = [
            models.Index(fields=["app_label", "model_name"], name="idx_audit_model"),
            models.Index(fields=["object_pk"], name="idx_audit_objectpk"),
            models.Index(fields=["created_at"], name="idx_audit_created"),
            models.Index(fields=["tenant", "created_at"], name="idx_audit_tenant_time"),
        ]

    def __str__(self) -> str:
        return (
            f"{self.created_at:%Y-%m-%d %H:%M} "
            f"{self.action} {self.app_label}.{self.model_name}#{self.object_pk}"
        )