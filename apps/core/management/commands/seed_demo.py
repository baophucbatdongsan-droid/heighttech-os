# apps/core/management/commands/seed_demo.py
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone


def _has_field(model, name: str) -> bool:
    try:
        return any(f.name == name for f in model._meta.get_fields())
    except Exception:
        return False


class Command(BaseCommand):
    help = "Seed demo data: users + company/brand/shop + memberships + shopmember + monthly performance"

    def add_arguments(self, parser):
        parser.add_argument("--company", default="Height Tech")
        parser.add_argument("--brand", default="Brand A")
        parser.add_argument("--shop", default="Shop 01")
        parser.add_argument("--admin-user", default="admin")
        parser.add_argument("--admin-pass", default="admin123")
        parser.add_argument("--client-user", default="client1")
        parser.add_argument("--client-pass", default="client123")
        parser.add_argument("--months", type=int, default=6)
        parser.add_argument("--reset-performance", action="store_true")

    def handle(self, *args, **opts):
        company_name = opts["company"]
        brand_name = opts["brand"]
        shop_name = opts["shop"]
        admin_user = opts["admin_user"]
        admin_pass = opts["admin_pass"]
        client_user = opts["client_user"]
        client_pass = opts["client_pass"]
        months = max(1, min(int(opts["months"]), 24))
        reset_perf = bool(opts.get("reset_performance"))

        User = get_user_model()

        # -------------------------
        # Users
        # -------------------------
        admin, created = User.objects.get_or_create(
            username=admin_user,
            defaults={"is_staff": True, "is_superuser": True},
        )
        if created:
            admin.set_password(admin_pass)
            admin.save()
            self.stdout.write(self.style.SUCCESS(f"✅ Created superuser: {admin_user}/{admin_pass}"))
        else:
            self.stdout.write(f"ℹ️ Superuser exists: {admin_user}")

        client, created = User.objects.get_or_create(
            username=client_user,
            defaults={"is_staff": False, "is_superuser": False},
        )
        if created:
            client.set_password(client_pass)
            client.save()
            self.stdout.write(self.style.SUCCESS(f"✅ Created client user: {client_user}/{client_pass}"))
        else:
            self.stdout.write(f"ℹ️ Client user exists: {client_user}")

        # -------------------------
        # Company / Brand / Shop
        # -------------------------
        from apps.companies.models import Company
        from apps.brands.models import Brand
        from apps.shops.models import Shop, ShopMember
        from apps.accounts.models import Membership
        from apps.performance.models import MonthlyPerformance

        company, _ = Company.objects.get_or_create(name=company_name)

        # Brand: thường có FK company
        brand_defaults = {}
        if _has_field(Brand, "company"):
            brand_defaults["company"] = company

        brand, _ = Brand.objects.get_or_create(name=brand_name, defaults=brand_defaults)

        # nếu brand đã tồn tại nhưng company chưa đúng thì set lại
        if _has_field(Brand, "company") and getattr(brand, "company_id", None) != company.id:
            brand.company = company
            brand.save(update_fields=["company"])

        shop_defaults = {}
        if _has_field(Shop, "brand"):
            shop_defaults["brand"] = brand
        if _has_field(Shop, "platform"):
            shop_defaults["platform"] = "Shopee"

        shop, _ = Shop.objects.get_or_create(name=shop_name, defaults=shop_defaults)

        if _has_field(Shop, "brand") and getattr(shop, "brand_id", None) != brand.id:
            shop.brand = brand
            shop.save(update_fields=["brand"])

        # ShopMember (owner + client)
        if _has_field(ShopMember, "role"):
            ShopMember.objects.get_or_create(
                shop=shop, user=admin,
                defaults={"role": "owner", "is_active": True},
            )
            ShopMember.objects.get_or_create(
                shop=shop, user=client,
                defaults={"role": "client", "is_active": True},
            )
        else:
            ShopMember.objects.get_or_create(shop=shop, user=admin)
            ShopMember.objects.get_or_create(shop=shop, user=client)

        # Membership: user-company-role
        Membership.objects.get_or_create(
            user=admin, company=company,
            defaults={"role": "founder", "is_active": True},
        )
        Membership.objects.get_or_create(
            user=client, company=company,
            defaults={"role": "operator", "is_active": True},
        )

        # -------------------------
        # MonthlyPerformance seed (IDEMPOTENT)
        # Key: (shop/company, month)
        # -------------------------
        today = timezone.now().date()
        first_of_this_month = today.replace(day=1)

        def month_shift(d: date, back: int) -> date:
            y = d.year
            m = d.month - back
            while m <= 0:
                m += 12
                y -= 1
            return date(y, m, 1)

        # optional: reset perf trước khi seed
        if reset_perf:
            qs = MonthlyPerformance.objects.all()
            if _has_field(MonthlyPerformance, "shop"):
                qs = qs.filter(shop=shop)
            elif _has_field(MonthlyPerformance, "company"):
                qs = qs.filter(company=company)
            deleted, _ = qs.delete()
            self.stdout.write(self.style.WARNING(f"🧹 Deleted MonthlyPerformance: {deleted}"))

        created_count = 0
        updated_count = 0

        for i in range(months):
            mdate = month_shift(first_of_this_month, i)

            # số demo
            revenue = Decimal("100000000") - Decimal(str(i * 5000000))
            if revenue < 0:
                revenue = Decimal("0")
            cost = revenue * Decimal("0.75")
            profit = revenue - cost
            net = profit * Decimal("0.85")

            lookup = {"month": mdate}
            if _has_field(MonthlyPerformance, "shop"):
                lookup["shop"] = shop
            elif _has_field(MonthlyPerformance, "company"):
                lookup["company"] = company

            defaults = {}
            if _has_field(MonthlyPerformance, "revenue"):
                defaults["revenue"] = revenue
            if _has_field(MonthlyPerformance, "cost"):
                defaults["cost"] = cost
            if _has_field(MonthlyPerformance, "profit"):
                defaults["profit"] = profit
            if _has_field(MonthlyPerformance, "company_net_profit"):
                defaults["company_net_profit"] = net

            obj, was_created = MonthlyPerformance.objects.update_or_create(
                **lookup,
                defaults=defaults,
            )
            if was_created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(self.style.SUCCESS("✅ Seed demo OK"))
        self.stdout.write(f"Company: {company.name}")
        self.stdout.write(f"Brand:   {brand.name}")
        self.stdout.write(f"Shop:    {shop.name}")
        self.stdout.write(f"MonthlyPerformance created: {created_count}, updated: {updated_count}")
        self.stdout.write("Login URLs:")
        self.stdout.write(" - http://127.0.0.1:8000/login/  (nếu bạn map core login)")
        self.stdout.write(" - http://127.0.0.1:8000/dashboard/")
        self.stdout.write(" - http://127.0.0.1:8000/founder/")
        self.stdout.write("API:")
        self.stdout.write(" - http://127.0.0.1:8000/api/v1/dashboard/")
        self.stdout.write(" - http://127.0.0.1:8000/api/v1/founder/")
        self.stdout.write(" - http://127.0.0.1:8000/api/v1/founder/shops/1/")