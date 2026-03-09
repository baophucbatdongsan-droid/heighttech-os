from __future__ import annotations

from django.db import models
from django.utils import timezone

from apps.core.managers import TenantAllManager, TenantManager


class ProductDailyStat(models.Model):
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
        related_name="product_daily_stats",
    )

    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        db_index=True,
        related_name="daily_stats",
    )

    stat_date = models.DateField(db_index=True)

    units_sold = models.PositiveIntegerField(default=0)
    orders_count = models.PositiveIntegerField(default=0)

    revenue = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    cost_of_goods = models.DecimalField(max_digits=16, decimal_places=2, default=0)

    ads_spend = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    booking_cost = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    livestream_revenue = models.DecimalField(max_digits=16, decimal_places=2, default=0)

    profit_estimate = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    roas_estimate = models.DecimalField(max_digits=12, decimal_places=4, default=0)

    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        ordering = ["-stat_date", "shop_id", "product_id"]
        indexes = [
            models.Index(fields=["tenant", "shop", "stat_date"], name="pds_t_sh_dt_idx"),
            models.Index(fields=["tenant", "product", "stat_date"], name="pds_t_pd_dt_idx"),
            models.Index(fields=["tenant", "stat_date"], name="pds_t_dt_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["shop", "product", "stat_date"],
                name="uq_shop_product_stat_date",
            )
        ]

    def __str__(self) -> str:
        return f"{self.shop_id} - {self.product_id} - {self.stat_date}"