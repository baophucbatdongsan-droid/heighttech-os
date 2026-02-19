# apps/brands/models.py
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.managers import TenantAllManager, TenantManager


class Brand(models.Model):
    """
    Brand thuộc Company.
    Company thuộc Tenant (multi-tenant SaaS).
    Một Brand có nhiều Shop.
    """

    # =========================
    # MULTI TENANT
    # =========================
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="brands",
        db_index=True,
        verbose_name="Tenant",
    )

    # =========================
    # RELATION
    # =========================
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="brands",
        verbose_name="Company",
    )

    # =========================
    # INFO
    # =========================
    name = models.CharField(max_length=255, verbose_name="Tên Brand")
    code = models.SlugField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Mã Brand (tuỳ chọn)",
    )

    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Đang hoạt động")

    created_at = models.DateTimeField(default=timezone.now, verbose_name="Ngày tạo")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Cập nhật")

    # managers
    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        verbose_name = "Brand"
        verbose_name_plural = "Brands"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["tenant"], name="idx_brand_tenant"),
            models.Index(fields=["tenant", "is_active"], name="idx_brand_tenant_active"),
            models.Index(fields=["company"], name="idx_brand_company"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "company", "name"],
                name="uq_brand_tenant_company_name",
            ),
        ]

    def __str__(self):
        company_name = getattr(self.company, "name", self.company_id)
        return f"{self.name} ({company_name})"

    def _resolve_tenant_from_company(self):
        c = getattr(self, "company", None)
        if c is None:
            return None

        # Ưu tiên company.tenant
        if getattr(c, "tenant_id", None):
            return getattr(c, "tenant", None)

        return None

    def save(self, *args, **kwargs):
        # auto sync tenant từ company nếu chưa set
        if not self.tenant_id:
            t = self._resolve_tenant_from_company()
            if t is not None:
                self.tenant = t
        super().save(*args, **kwargs)


class BrandMember(models.Model):
    """
    Mapping user ↔ brand (portal/ops).
    Role trong phạm vi Brand.
    ✅ Có tenant để scoping chuẩn.
    """

    ROLE_OWNER = "owner"
    ROLE_MANAGER = "manager"
    ROLE_VIEWER = "viewer"

    ROLE_CHOICES = [
        (ROLE_OWNER, "Owner"),
        (ROLE_MANAGER, "Manager"),
        (ROLE_VIEWER, "Viewer"),
    ]

    # =========================
    # MULTI TENANT
    # =========================
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="brand_members",
        db_index=True,
        verbose_name="Tenant",
    )

    # =========================
    # RELATION
    # =========================
    brand = models.ForeignKey(
        "brands.Brand",
        on_delete=models.CASCADE,
        related_name="members",
        verbose_name="Brand",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="brand_memberships",
        verbose_name="User",
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_VIEWER,
        verbose_name="Role",
    )

    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Active")
    created_at = models.DateTimeField(default=timezone.now)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        verbose_name = "Brand member"
        verbose_name_plural = "Brand members"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["tenant"], name="idx_brandmember_tenant"),
            models.Index(fields=["user"], name="idx_brandmember_user"),
            models.Index(fields=["is_active"], name="idx_brandmember_active"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["brand", "user"],
                name="uq_brandmember_brand_user",
            ),
        ]

    def __str__(self):
        username = getattr(self.user, "username", self.user_id)
        brand_name = getattr(self.brand, "name", self.brand_id)
        return f"{username} -> {brand_name} ({self.role})"

    def save(self, *args, **kwargs):
        # auto sync tenant từ brand nếu chưa set
        if not self.tenant_id and self.brand_id:
            try:
                self.tenant_id = self.brand.tenant_id
            except Exception:
                pass
        super().save(*args, **kwargs)