from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.products.models import Product
from apps.products.models_stats import ProductDailyStat
from apps.shop_services.models import ShopServiceSubscription
from apps.work.models import WorkItem

try:
    from apps.contracts.models import Contract, ContractMilestone, ContractPayment, ContractBookingItem
except Exception:
    Contract = None
    ContractMilestone = None
    ContractPayment = None
    ContractBookingItem = None

try:
    from apps.shops.models import Shop
except Exception:
    Shop = None


def d(v) -> Decimal:
    return Decimal(str(v))


class Command(BaseCommand):
    help = "Seed demo data cho 1 shop: products, daily stats, services, tasks, contracts"

    def add_arguments(self, parser):
        parser.add_argument("--tenant-id", type=int, required=True)
        parser.add_argument("--shop-id", type=int, required=True)
        parser.add_argument("--company-id", type=int, required=False, default=None)
        parser.add_argument("--days", type=int, required=False, default=30)
        parser.add_argument("--products", type=int, required=False, default=10)
        parser.add_argument("--clear", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        tenant_id = int(options["tenant_id"])
        shop_id = int(options["shop_id"])
        company_id = options.get("company_id")
        days = max(7, int(options["days"] or 30))
        products_n = max(3, int(options["products"] or 10))
        should_clear = bool(options.get("clear"))

        if Shop is None:
            raise CommandError("Không tìm thấy apps.shops.models.Shop")

        try:
            shop = Shop.objects_all.get(id=shop_id, tenant_id=tenant_id)
        except Exception:
            raise CommandError(f"Không tìm thấy shop_id={shop_id}, tenant_id={tenant_id}")

        if not company_id:
            company_id = getattr(shop, "company_id", None)

        if should_clear:
            self._clear_demo_data(tenant_id=tenant_id, shop_id=shop_id)

        products = self._seed_products(
            tenant_id=tenant_id,
            company_id=company_id,
            shop_id=shop_id,
            n=products_n,
        )

        self._seed_product_stats(
            tenant_id=tenant_id,
            company_id=company_id,
            shop_id=shop_id,
            products=products,
            days=days,
        )

        self._seed_shop_services(
            tenant_id=tenant_id,
            company_id=company_id,
            shop_id=shop_id,
        )

        self._seed_work_items(
            tenant_id=tenant_id,
            company_id=company_id,
            shop_id=shop_id,
        )

        self._seed_contracts(
            tenant_id=tenant_id,
            company_id=company_id,
            shop_id=shop_id,
        )

        self.stdout.write(self.style.SUCCESS(
            f"Seed xong demo shop_id={shop_id}, tenant_id={tenant_id}"
        ))

    def _clear_demo_data(self, *, tenant_id: int, shop_id: int):
        ProductDailyStat.objects_all.filter(tenant_id=tenant_id, shop_id=shop_id).delete()
        Product.objects_all.filter(tenant_id=tenant_id, shop_id=shop_id, sku__startswith="DEMO-").delete()
        ShopServiceSubscription.objects_all.filter(tenant_id=tenant_id, shop_id=shop_id).delete()
        WorkItem.objects_all.filter(tenant_id=tenant_id, shop_id=shop_id, title__startswith="[DEMO]").delete()

        if Contract is not None:
            demo_contracts = Contract.objects_all.filter(
                tenant_id=tenant_id,
                code__startswith="DEMO-",
            )
            if ContractBookingItem is not None:
                ContractBookingItem.objects_all.filter(contract__in=demo_contracts).delete()
            if ContractMilestone is not None:
                ContractMilestone.objects_all.filter(contract__in=demo_contracts).delete()
            if ContractPayment is not None:
                ContractPayment.objects_all.filter(contract__in=demo_contracts).delete()
            demo_contracts.delete()

    def _seed_products(self, *, tenant_id: int, company_id, shop_id: int, n: int):
        names = [
            "Serum Collagen", "Son Velvet", "Kem Chống Nắng", "Mask Ngủ",
            "Tẩy Trang", "Kem Dưỡng", "Toner B5", "Sữa Rửa Mặt",
            "Tinh Chất C", "Cushion Glow", "Kem Body", "Xịt Khoáng",
        ]
        products = []

        for i in range(1, n + 1):
            sku = f"DEMO-SKU-{i:03d}"
            name = f"{names[(i - 1) % len(names)]} {i}"
            price = d(random.choice([99000, 149000, 199000, 249000, 299000, 349000]))
            cost = (price * d("0.38")).quantize(d("1"))
            stock = random.randint(3, 80)

            obj, _ = Product.objects_all.update_or_create(
                tenant_id=tenant_id,
                shop_id=shop_id,
                sku=sku,
                defaults={
                    "company_id": company_id,
                    "name": name,
                    "price": price,
                    "cost": cost,
                    "stock": stock,
                    "status": "active",
                    "meta": {"source": "seed_demo_shop"},
                },
            )
            products.append(obj)

        return products

    def _seed_product_stats(self, *, tenant_id: int, company_id, shop_id: int, products, days: int):
        today = timezone.localdate()

        for offset in range(days):
            stat_date = today - timedelta(days=offset)

            for p in products:
                units = random.randint(0, 12)
                orders = max(0, units - random.randint(0, 3))
                revenue = (d(p.price) * d(units)).quantize(d("1"))
                ads_spend = d(random.choice([0, 50000, 100000, 150000, 250000, 400000]))
                booking_cost = d(random.choice([0, 0, 0, 50000, 80000, 120000]))
                livestream_revenue = d(random.choice([0, 0, 200000, 400000, 800000]))
                cogs = (d(p.cost) * d(units)).quantize(d("1"))
                profit = revenue - cogs - ads_spend - booking_cost
                roas = (revenue / ads_spend).quantize(d("0.0001")) if ads_spend > 0 else d("0")

                ProductDailyStat.objects_all.update_or_create(
                    tenant_id=tenant_id,
                    shop_id=shop_id,
                    product_id=p.id,
                    stat_date=stat_date,
                    defaults={
                        "company_id": company_id,
                        "units_sold": units,
                        "orders_count": orders,
                        "revenue": revenue,
                        "cost_of_goods": cogs,
                        "ads_spend": ads_spend,
                        "booking_cost": booking_cost,
                        "livestream_revenue": livestream_revenue,
                        "profit_estimate": profit,
                        "roas_estimate": roas,
                        "meta": {"source": "seed_demo_shop"},
                    },
                )

    def _seed_shop_services(self, *, tenant_id: int, company_id, shop_id: int):
        today = timezone.localdate()
        demo_services = [
            ("booking", "active", today - timedelta(days=7), today + timedelta(days=30)),
            ("livestream", "active", today - timedelta(days=3), today + timedelta(days=20)),
            ("channel_build", "paused", today - timedelta(days=20), today + timedelta(days=40)),
            ("ads", "active", today - timedelta(days=10), today + timedelta(days=60)),
        ]

        for service_code, status, start_date, end_date in demo_services:
            ShopServiceSubscription.objects_all.update_or_create(
                tenant_id=tenant_id,
                shop_id=shop_id,
                service_code=service_code,
                contract=None,
                defaults={
                    "company_id": company_id,
                    "status": status,
                    "service_name": "",
                    "start_date": start_date,
                    "end_date": end_date,
                    "note": "Demo service seeded automatically",
                    "meta": {"source": "seed_demo_shop"},
                },
            )

    def _seed_work_items(self, *, tenant_id: int, company_id, shop_id: int):
        now = timezone.now()

        demo_tasks = [
            ("[DEMO] Kiểm tra SKU ROAS thấp", 3, now + timedelta(hours=8), "todo"),
            ("[DEMO] Bổ sung tồn kho SKU bán chạy", 4, now + timedelta(days=1), "doing"),
            ("[DEMO] Chốt lịch livestream tuần này", 3, now + timedelta(days=2), "todo"),
            ("[DEMO] Rà soát task quá hạn", 4, now - timedelta(days=1), "todo"),
        ]

        for title, priority, due_at, status in demo_tasks:
            WorkItem.objects_all.update_or_create(
                tenant_id=tenant_id,
                shop_id=shop_id,
                title=title,
                defaults={
                    "company_id": company_id,
                    "status": status,
                    "priority": priority,
                    "due_at": due_at,
                    "description": "Demo task seeded automatically",
                    "type": getattr(WorkItem.Type, "TASK", "task"),
                },
            )

    def _seed_contracts(self, *, tenant_id: int, company_id, shop_id: int):
        if Contract is None:
            return

        today = timezone.localdate()
        start_dt = timezone.make_aware(
            timezone.datetime.combine(today - timedelta(days=15), timezone.datetime.min.time()),
            timezone.get_current_timezone(),
        )

        contract, _ = Contract.objects_all.update_or_create(
            tenant_id=tenant_id,
            code=f"DEMO-HD-{shop_id}",
            defaults={
                "company_id": company_id,
                "name": f"Hợp đồng demo shop {shop_id}",
                "contract_type": "operations",
                "start_date": today - timedelta(days=15),
                "end_date": today + timedelta(days=60),
                "status": getattr(getattr(Contract, "Status", object), "ACTIVE", "active"),
                "total_value": d("25000000"),
            },
        )

        # gắn shop vào contract nếu model qua bảng M2M có related manager
        try:
            contract.contract_shops.get_or_create(shop_id=shop_id)
        except Exception:
            pass

        if ContractPayment is not None:
            for i in range(1, 4):
                due_dt = timezone.make_aware(
                    timezone.datetime.combine(today + timedelta(days=(i - 2) * 5), timezone.datetime.max.time().replace(microsecond=0)),
                    timezone.get_current_timezone(),
                )
                ContractPayment.objects_all.update_or_create(
                    tenant_id=tenant_id,
                    contract_id=contract.id,
                    title=f"Thanh toán đợt {i}",
                    defaults={
                        "due_at": due_dt,
                        "amount": d("5000000") * i,
                        "status": "pending" if i != 1 else "partial",
                    },
                )

        if ContractMilestone is not None:
            for i in range(1, 4):
                due_dt = timezone.make_aware(
                    timezone.datetime.combine(today + timedelta(days=(i - 1) * 4), timezone.datetime.max.time().replace(microsecond=0)),
                    timezone.get_current_timezone(),
                )
                ContractMilestone.objects_all.update_or_create(
                    tenant_id=tenant_id,
                    contract_id=contract.id,
                    title=f"Milestone demo {i}",
                    defaults={
                        "shop_id": shop_id,
                        "due_at": due_dt,
                        "status": "todo" if i != 1 else "doing",
                    },
                )

        if ContractBookingItem is not None:
            for i in range(1, 3):
                air_dt = timezone.make_aware(
                    timezone.datetime.combine(today + timedelta(days=i), timezone.datetime.max.time().replace(microsecond=0)),
                    timezone.get_current_timezone(),
                )
                payout_dt = timezone.make_aware(
                    timezone.datetime.combine(today + timedelta(days=i + 2), timezone.datetime.max.time().replace(microsecond=0)),
                    timezone.get_current_timezone(),
                )
                ContractBookingItem.objects_all.update_or_create(
                    tenant_id=tenant_id,
                    contract_id=contract.id,
                    shop_id=shop_id,
                    koc_name=f"KOC Demo {i}",
                    defaults={
                        "air_date": air_dt,
                        "payout_due_at": payout_dt,
                        "payout_amount": d("1200000") * i,
                        "payout_status": "pending",
                        "video_link": "" if i == 1 else "https://example.com/video-demo",
                    },
                )