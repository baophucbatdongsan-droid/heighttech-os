from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.managers import TenantManager, TenantAllManager
from apps.companies.models import Company
from apps.shops.models import Shop


class Channel(models.Model):
    """
    Kênh marketing / bán hàng của Company (TikTok, Facebook, YouTube, etc.)
    """
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="channels",
        db_index=True,
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="channels",
        db_index=True,
    )

    TYPE_TIKTOK = "tiktok"
    TYPE_FACEBOOK = "facebook"
    TYPE_YOUTUBE = "youtube"
    TYPE_SHOPEE = "shopee"
    TYPE_LAZADA = "lazada"
    TYPE_OTHER = "other"

    TYPE_CHOICES = [
        (TYPE_TIKTOK, "TikTok"),
        (TYPE_FACEBOOK, "Facebook"),
        (TYPE_YOUTUBE, "YouTube"),
        (TYPE_SHOPEE, "Shopee"),
        (TYPE_LAZADA, "Lazada"),
        (TYPE_OTHER, "Other"),
    ]

    type = models.CharField(max_length=30, choices=TYPE_CHOICES, default=TYPE_OTHER, db_index=True)
    name = models.CharField(max_length=255, db_index=True)

    is_active = models.BooleanField(default=True, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_channels",
    )

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["tenant", "company"], name="idx_channel_tenant_company"),
            models.Index(fields=["tenant", "type"], name="idx_channel_tenant_type"),
            models.Index(fields=["tenant", "is_active"], name="idx_channel_tenant_active"),
        ]

    def save(self, *args, **kwargs):
        if not self.tenant_id and self.company_id:
            self.tenant_id = self.company.tenant_id
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} ({self.type})"


class ChannelAccount(models.Model):
    """
    Tài khoản cụ thể của kênh (VD: TikTok account, FB page, etc.)
    """
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="channel_accounts", db_index=True)
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="accounts", db_index=True)

    account_name = models.CharField(max_length=255, blank=True, default="")
    external_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    url = models.URLField(blank=True, default="")

    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["tenant", "channel"], name="idx_chacc_tenant_channel"),
        ]

    def save(self, *args, **kwargs):
        if not self.tenant_id and self.channel_id:
            self.tenant_id = self.channel.tenant_id
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.account_name or f"Account#{self.pk}"


class ChannelShopLink(models.Model):
    """
    Link kênh phục vụ shop nào (đa-nhiều).
    """
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="channel_shop_links", db_index=True)
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="shop_links", db_index=True)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="channel_links", db_index=True)

    created_at = models.DateTimeField(default=timezone.now)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "channel", "shop"], name="uq_channel_shop_link"),
        ]
        indexes = [
            models.Index(fields=["tenant", "channel"], name="idx_chshop_tenant_channel"),
            models.Index(fields=["tenant", "shop"], name="idx_chshop_tenant_shop"),
        ]

    def save(self, *args, **kwargs):
        if not self.tenant_id and self.channel_id:
            self.tenant_id = self.channel.tenant_id
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.channel_id} - {self.shop_id}"