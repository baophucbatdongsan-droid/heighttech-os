from __future__ import annotations

from django.conf import settings
from django.db import models


class ShopUserLink(models.Model):
    ROLE_OWNER = "owner"
    ROLE_LEADER = "leader"
    ROLE_STAFF = "staff"
    ROLE_CLIENT = "client"

    ROLE_CHOICES = [
        (ROLE_OWNER, "Owner"),
        (ROLE_LEADER, "Leader"),
        (ROLE_STAFF, "Staff"),
        (ROLE_CLIENT, "Client"),
    ]

    # đồng bộ với hệ tenant của bạn (int tenant_id)
    tenant_id = models.IntegerField(db_index=True)

    shop = models.ForeignKey("shops.Shop", on_delete=models.CASCADE, related_name="user_links")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shop_links")

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_STAFF)
    is_active = models.BooleanField(default=True)

    # bật client-portal cho user ở shop này
    is_client = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("shop", "user")]
        indexes = [
            models.Index(fields=["tenant_id", "shop"]),
            models.Index(fields=["tenant_id", "user"]),
            models.Index(fields=["tenant_id", "is_client"]),
            models.Index(fields=["tenant_id", "role"]),
        ]

    def __str__(self) -> str:
        return f"ShopUserLink(shop={self.shop_id}, user={self.user_id}, role={self.role})"