# FILE: apps/sales/management/commands/seed_sales_demo.py
from __future__ import annotations

import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from apps.sales.models import DailySales, SkuSalesDaily
from apps.shops.models import Shop


class Command(BaseCommand):
    help = "Seed demo DailySales + SkuSalesDaily for a shop"

    def add_arguments(self, parser):
        parser.add_argument("--shop_id", type=int, required=True)
        parser.add_argument("--days", type=int, default=14)

    def handle(self, *args, **opts):
        shop_id = int(opts["shop_id"])
        days = int(opts["days"])

        shop = Shop.objects_all.select_related("tenant").get(id=shop_id)
        tid = shop.tenant_id

        today = date.today()

        skus = ["SKU-A01", "SKU-A02", "SKU-B11", "SKU-C09", "SKU-D20"]

        for i in range(days):
            d = today - timedelta(days=i)

            revenue = round(random.uniform(5_000_000, 45_000_000), 2)
            orders = random.randint(10, 120)
            spend = round(revenue * random.uniform(0.08, 0.22), 2)
            roas = round(float(revenue) / float(spend) if spend else 0, 2)

            DailySales.objects_all.update_or_create(
                tenant_id=tid,
                shop_id=shop_id,
                date=d,
                defaults={"revenue": revenue, "orders": orders, "spend": spend, "roas": roas},
            )

            # sku breakdown
            for sku in skus:
                sku_rev = round(revenue * random.uniform(0.05, 0.35), 2)
                sku_orders = random.randint(1, max(1, int(orders / 3)))
                sku_units = sku_orders + random.randint(0, sku_orders)

                SkuSalesDaily.objects_all.update_or_create(
                    tenant_id=tid,
                    shop_id=shop_id,
                    date=d,
                    sku=sku,
                    defaults={"revenue": sku_rev, "orders": sku_orders, "units": sku_units},
                )

        self.stdout.write(self.style.SUCCESS(f"Seeded demo sales for shop_id={shop_id}, days={days}"))