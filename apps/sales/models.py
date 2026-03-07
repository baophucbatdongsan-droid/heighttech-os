# FILE: apps/sales/models.py
from __future__ import annotations

from django.db import models
from django.utils import timezone

from apps.core.managers import TenantAllManager, TenantManager


class DailySales(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, db_index=True)
    shop = models.ForeignKey("shops.Shop", on_delete=models.CASCADE, db_index=True)

    date = models.DateField(db_index=True)

    revenue = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    orders = models.PositiveIntegerField(default=0)
    spend = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    roas = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    created_at = models.DateTimeField(default=timezone.now)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        ordering = ["-date"]
        indexes = [
            models.Index(fields=["tenant", "shop", "date"], name="ds_t_shop_dt_idx"),
            models.Index(fields=["tenant", "date"], name="ds_t_dt_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "shop", "date"], name="uq_ds_t_shop_date")
        ]

    def __str__(self) -> str:
        return f"DailySales shop={self.shop_id} {self.date}"


class SkuSalesDaily(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, db_index=True)
    shop = models.ForeignKey("shops.Shop", on_delete=models.CASCADE, db_index=True)

    date = models.DateField(db_index=True)
    sku = models.CharField(max_length=120, db_index=True)

    revenue = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    orders = models.PositiveIntegerField(default=0)
    units = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(default=timezone.now)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        ordering = ["-date", "-revenue"]
        indexes = [
            models.Index(fields=["tenant", "shop", "date"], name="ssd_t_shop_dt_idx"),
            models.Index(fields=["tenant", "shop", "sku"], name="ssd_t_shop_sku_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "shop", "date", "sku"], name="uq_ssd_t_shop_date_sku")
        ]

    def __str__(self) -> str:
        return f"SkuSalesDaily shop={self.shop_id} {self.date} sku={self.sku}"