# apps/shops/models.py
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.managers import TenantAllManager, TenantManager


class Shop(models.Model):
    """
    Shop thuộc Brand.
    Brand thuộc Company.
    Company thuộc Tenant (multi-tenant SaaS).
    """

    STATUS_ACTIVE = "active"
    STATUS_PAUSED = "paused"
    STATUS_ENDED = "ended"

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_PAUSED, "Paused"),
        (STATUS_ENDED, "Ended"),
    ]

    # =========================
    # MULTI TENANT
    # =========================
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="shops",
        db_index=True,
        verbose_name="Tenant",
    )

    # =========================
    # RELATION
    # =========================
    brand = models.ForeignKey(
        "brands.Brand",
        on_delete=models.CASCADE,
        related_name="shops",
        verbose_name="Brand",
    )

    # =========================
    # INFO
    # =========================
    name = models.CharField(max_length=255, verbose_name="Tên shop")

    platform = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Sàn (Shopee/TikTok/Lazada...)",
    )

    code = models.SlugField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Mã shop (tuỳ chọn)",
    )

    description = models.TextField(blank=True, null=True, verbose_name="Mô tả")

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
        verbose_name="Trạng thái",
    )

    # =========================
    # RULE ENGINE (code-based, versioned)
    # =========================
    industry_code = models.CharField(
        max_length=64,
        default="default",
        db_index=True,
        verbose_name="Industry code",
        help_text="Ví dụ: default, ecommerce, agency, ...",
    )

    rule_version = models.CharField(
        max_length=32,
        default="v1",
        db_index=True,
        verbose_name="Rule version",
        help_text="Ví dụ: v1, v2, ... (code-based rules)",
    )

    started_at = models.DateField(blank=True, null=True, verbose_name="Ngày bắt đầu")
    ended_at = models.DateField(blank=True, null=True, verbose_name="Ngày kết thúc")

    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Đang hoạt động")

    created_at = models.DateTimeField(default=timezone.now, verbose_name="Ngày tạo")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Cập nhật")

    # =========================
    # MANAGERS (tenant scoped)
    # =========================
    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        verbose_name = "Shop"
        verbose_name_plural = "Shops"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["tenant"], name="idx_shop_tenant"),
            models.Index(fields=["tenant", "is_active"], name="idx_shop_tenant_active"),
            models.Index(fields=["brand"], name="idx_shop_brand"),
            models.Index(fields=["status"], name="idx_shop_status"),
            models.Index(fields=["tenant", "industry_code", "rule_version"], name="idx_shop_rule"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "brand", "name"],
                name="uq_shop_tenant_brand_name",
            ),
        ]

    def __str__(self) -> str:
        brand_name = getattr(self.brand, "name", self.brand_id)
        return f"{self.name} ({brand_name})"

    def _resolve_tenant_from_brand(self):
        """
        brand -> company -> tenant
        Ưu tiên không query thêm nếu object đã load sẵn.
        """
        b = getattr(self, "brand", None)
        if b is None:
            return None

        # Nếu Brand đã có tenant
        if getattr(b, "tenant_id", None):
            return getattr(b, "tenant", None)

        # Fallback: brand.company.tenant
        c = getattr(b, "company", None)
        if c is not None and getattr(c, "tenant_id", None):
            return getattr(c, "tenant", None)

        return None

    def save(self, *args, **kwargs):
        # auto sync tenant từ brand nếu chưa set
        if not self.tenant_id:
            t = self._resolve_tenant_from_brand()
            if t is not None:
                self.tenant = t
        super().save(*args, **kwargs)


class ShopMember(models.Model):
    """
    Mapping user ↔ shop (portal/ops).
    Role trong phạm vi Shop.
    Có tenant để scoping chuẩn.
    """

    ROLE_OWNER = "owner"
    ROLE_MANAGER = "manager"
    ROLE_OPERATOR = "operator"
    ROLE_VIEWER = "viewer"

    ROLE_CHOICES = [
        (ROLE_OWNER, "Owner"),
        (ROLE_MANAGER, "Manager"),
        (ROLE_OPERATOR, "Operator"),
        (ROLE_VIEWER, "Viewer"),
    ]

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="shop_members",
        db_index=True,
        verbose_name="Tenant",
    )

    shop = models.ForeignKey(
        "shops.Shop",
        on_delete=models.CASCADE,
        related_name="members",
        verbose_name="Shop",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="shop_memberships",
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
        verbose_name = "Shop member"
        verbose_name_plural = "Shop members"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["tenant"], name="idx_shopmember_tenant"),
            models.Index(fields=["tenant", "user"], name="idx_shopmember_tenant_user"),
            models.Index(fields=["tenant", "shop"], name="idx_shopmember_tenant_shop"),
            models.Index(fields=["is_active"], name="idx_shopmember_active"),
        ]
        constraints = [
            # OS-grade: tránh collision khi sau này cross-tenant / import data
            models.UniqueConstraint(
                fields=["tenant", "shop", "user"],
                name="uq_shopmember_tenant_shop_user",
            ),
        ]

    def __str__(self) -> str:
        username = getattr(self.user, "username", self.user_id)
        shop_name = getattr(self.shop, "name", self.shop_id)
        return f"{username} -> {shop_name} ({self.role})"

    def save(self, *args, **kwargs):
        # ✅ FINAL: auto sync tenant từ shop (bỏ hack chain)
        if not self.tenant_id and self.shop_id:
            try:
                # dùng Shop._base_manager để bypass TenantManager scoping
                ShopModel = self._meta.get_field("shop").remote_field.model
                self.tenant_id = ShopModel._base_manager.only("tenant_id").get(id=self.shop_id).tenant_id
            except Exception:
                # fallback: nếu self.shop đã load được
                try:
                    self.tenant_id = self.shop.tenant_id
                except Exception:
                    pass

        super().save(*args, **kwargs)