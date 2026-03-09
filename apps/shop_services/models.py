from __future__ import annotations

from django.db import models
from django.utils import timezone

from apps.core.managers import TenantAllManager, TenantManager


class ShopServiceSubscription(models.Model):
    class ServiceCode(models.TextChoices):
        BOOKING = "booking", "Booking"
        CHANNEL_BUILD = "channel_build", "Xây kênh"
        LIVESTREAM = "livestream", "Livestream"
        OPERATIONS = "operations", "Vận hành"
        ADS = "ads", "Ads"
        KOC = "koc", "KOC"
        CONTENT = "content", "Content"
        OTHER = "other", "Khác"

    class Status(models.TextChoices):
        DRAFT = "draft", "Nháp"
        ACTIVE = "active", "Đang dùng"
        PAUSED = "paused", "Tạm dừng"
        ENDED = "ended", "Kết thúc"
        CANCELLED = "cancelled", "Huỷ"

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        db_index=True,
    )
    company = models.ForeignKey(
        "companies.Company",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_index=True,
        related_name="shop_service_subscriptions",
    )
    shop = models.ForeignKey(
        "shops.Shop",
        on_delete=models.CASCADE,
        db_index=True,
        related_name="service_subscriptions",
    )

    service_code = models.CharField(
        max_length=40,
        choices=ServiceCode.choices,
        default=ServiceCode.OTHER,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )

    service_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Tên hiển thị dịch vụ nếu cần custom riêng",
    )

    start_date = models.DateField(null=True, blank=True, db_index=True)
    end_date = models.DateField(null=True, blank=True, db_index=True)

    contract = models.ForeignKey(
        "contracts.Contract",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_index=True,
        related_name="shop_service_subscriptions",
        help_text="Liên kết hợp đồng nếu dịch vụ này đi theo hợp đồng cụ thể",
    )

    owner = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_index=True,
        related_name="owned_shop_services",
        help_text="Người phụ trách dịch vụ này",
    )

    note = models.TextField(blank=True, default="")
    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        ordering = ["shop_id", "service_code", "-id"]
        indexes = [
            models.Index(fields=["tenant", "shop", "status"], name="ssub_t_sh_st_idx"),
            models.Index(fields=["tenant", "service_code", "status"], name="ssub_t_sv_st_idx"),
            models.Index(fields=["tenant", "start_date", "end_date"], name="ssub_t_sd_ed_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["shop", "service_code", "contract"],
                name="uq_shop_service_contract",
            )
        ]

    def __str__(self) -> str:
        svc = self.service_name or self.get_service_code_display()
        return f"{self.shop_id} - {svc} - {self.status}"