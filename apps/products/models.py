from __future__ import annotations

from django.db import models
from django.utils import timezone

from apps.core.managers import TenantManager, TenantAllManager


class Product(models.Model):

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
    )

    shop = models.ForeignKey(
        "shops.Shop",
        on_delete=models.CASCADE,
        db_index=True,
        related_name="products",
    )

    sku = models.CharField(
        max_length=120,
        db_index=True,
    )

    name = models.CharField(
        max_length=255
    )

    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    stock = models.IntegerField(
        default=0
    )

    status = models.CharField(
        max_length=20,
        default="active",
        db_index=True,
    )

    meta = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        default=timezone.now,
        db_index=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        ordering = ["shop_id", "sku"]
        indexes = [
            models.Index(fields=["tenant", "shop"]),
            models.Index(fields=["tenant", "sku"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["shop", "sku"],
                name="uq_shop_sku"
            )
        ]

    def __str__(self):
        return f"{self.shop_id} - {self.sku}"