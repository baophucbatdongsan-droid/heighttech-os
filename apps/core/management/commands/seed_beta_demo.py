# apps/core/management/commands/seed_beta_demo.py
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Membership, ROLE_FOUNDER, ROLE_HEAD, ROLE_OPERATOR
from apps.brands.models import Brand
from apps.companies.models import Company
from apps.performance.models import MonthlyPerformance
from apps.shops.models import Shop, ShopMember
from apps.tenants.models import Tenant, TenantDomain


def d(x) -> Decimal:
    # an toàn khi nhận float/int/Decimal
    return Decimal(str(x or "0"))


def month_start(dt: date) -> date:
    return date(dt.year, dt.month, 1)


def prev_months(n: int) -> list[date]:
    today = timezone.now().date()
    y, m = today.year, today.month
    out: list[date] = []
    for i in range(n):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        out.append(date(yy, mm, 1))
    return sorted(out)


@dataclass(frozen=True)
class ShopProfile:
    kind: str  # "grow" | "loss" | "low_margin" | "spike" | "normal"


class Command(BaseCommand):
    help = "Seed beta demo data (tenant/company/brand/shop/monthly performance) for local"

    def add_arguments(self, parser):
        parser.add_argument("--tenant-id", type=int, default=None)
        parser.add_argument("--months", type=int, default=12)
        parser.add_argument("--shops-per-brand", type=int, default=5)
        parser.add_argument("--wipe", action="store_true", help="Wipe demo data (safe scope) then seed")

    @transaction.atomic
    def handle(self, *args, **opts):
        months = int(opts["months"])
        shops_per_brand = int(opts["shops_per_brand"])

        # ==========================================================
        # 1) Resolve tenant
        # ==========================================================
        tenant = None
        tid = opts.get("tenant_id")
        if tid:
            tenant = Tenant.objects.filter(id=tid).first()
        if tenant is None:
            tenant = Tenant.objects.filter(is_active=True).order_by("id").first()
        if tenant is None:
            tenant = Tenant.objects.create(name="Demo Tenant", is_active=True, status="active")

        # domains for local convenience
        for dom in ("localhost", "127.0.0.1", "testserver"):
            try:
                TenantDomain.objects.get_or_create(
                    tenant=tenant,
                    domain=dom,
                    defaults={"is_active": True},
                )
            except Exception:
                pass

        # ==========================================================
        # 2) Create demo users
        # ==========================================================
        User = get_user_model()

        founder, _ = User.objects.get_or_create(
            username="founder",
            defaults={"is_superuser": True, "is_staff": True},
        )
        if not founder.check_password("123456"):
            founder.set_password("123456")
            founder.save(update_fields=["password"])

        admin, _ = User.objects.get_or_create(
            username="admin",
            defaults={"is_staff": True, "is_superuser": False},
        )
        if not admin.check_password("123456"):
            admin.set_password("123456")
            admin.save(update_fields=["password"])

        operator, _ = User.objects.get_or_create(username="operator")
        if not operator.check_password("123456"):
            operator.set_password("123456")
            operator.save(update_fields=["password"])

        client_u, _ = User.objects.get_or_create(username="client")
        if not client_u.check_password("123456"):
            client_u.set_password("123456")
            client_u.save(update_fields=["password"])

        # ==========================================================
        # 3) WIPE (IMPORTANT): use _base_manager to avoid scoped manager issues
        #    Only wipe rows tied to this tenant (safe scope)
        # ==========================================================
        if opts.get("wipe"):
            # NOTE: MonthlyPerformance has TenantManager() => MUST use _base_manager
            MonthlyPerformance._base_manager.filter(tenant_id=tenant.id).delete()

            # Delete dependents before parents
            ShopMember._base_manager.filter(shop__tenant_id=tenant.id).delete()
            Shop._base_manager.filter(tenant_id=tenant.id).delete()
            Brand._base_manager.filter(company__tenant_id=tenant.id).delete()
            Membership._base_manager.filter(tenant_id=tenant.id).delete()
            Company._base_manager.filter(tenant_id=tenant.id).delete()

        # ==========================================================
        # 4) Companies / Brands / Shops
        # ==========================================================
        companies: list[Company] = []
        for i in range(1, 4):
            c, _ = Company.objects.get_or_create(
                tenant=tenant,
                name=f"Agency Company {i}",
                defaults={},
            )
            companies.append(c)

        # memberships (internal)
        for c in companies:
            Membership._base_manager.get_or_create(
                tenant=tenant, user=founder, company=c, defaults={"role": ROLE_FOUNDER}
            )
            Membership._base_manager.get_or_create(
                tenant=tenant, user=admin, company=c, defaults={"role": ROLE_HEAD}
            )
            Membership._base_manager.get_or_create(
                tenant=tenant, user=operator, company=c, defaults={"role": ROLE_OPERATOR}
            )

        all_shops: list[Shop] = []
        for c in companies:
            for b in range(1, 3):
                brand, _ = Brand.objects.get_or_create(
                    company=c,
                    name=f"{c.name} • Brand {b}",
                    defaults={},
                )

                for s in range(1, shops_per_brand + 1):
                    shop, _ = Shop.objects.get_or_create(
                        tenant=tenant,
                        brand=brand,
                        name=f"{brand.name} • Shop {s}",
                        defaults={
                            "industry_code": random.choice(["default", "fashion", "beauty", "electronics"]),
                            "rule_version": "v1",
                        },
                    )
                    all_shops.append(shop)

        # ==========================================================
        # 5) client user owns 3 shops
        # ==========================================================
        for shop in all_shops[:3]:
            ShopMember._base_manager.get_or_create(
                user=client_u,
                shop=shop,
                defaults={"is_active": True},
            )

        # ==========================================================
        # 6) profile assignment (to generate alerts)
        # ==========================================================
        profiles: dict[int, ShopProfile] = {}
        kinds = (["grow"] * 6) + (["loss"] * 6) + (["low_margin"] * 6) + (["spike"] * 2)
        random.shuffle(kinds)
        for idx, shop in enumerate(all_shops):
            profiles[shop.id] = ShopProfile(kind=kinds[idx] if idx < len(kinds) else "normal")

        # ==========================================================
        # 7) generate performances (IMPORTANT): use _base_manager for upsert too
        # ==========================================================
        ms = prev_months(months)
        created_rows = 0

        mp_mgr = MonthlyPerformance._base_manager  # <- critical fix

        for shop in all_shops:
            prof = profiles[shop.id].kind
            base_rev = d(random.randint(200_000_000, 2_500_000_000))  # 200m -> 2.5b
            fixed_fee = d(random.choice([0, 5_000_000, 10_000_000, 15_000_000, 20_000_000]))
            vat = d(random.choice([0, 8, 10]))
            sale_pct = d(random.choice([3, 4, 5, 6]))

            rev = base_rev
            for m in ms:
                # pattern by profile
                if prof == "grow":
                    rev = rev * d(random.uniform(1.05, 1.18))
                    cost = rev * d(random.uniform(0.55, 0.75))
                elif prof == "loss":
                    rev = rev * d(random.uniform(0.95, 1.05))
                    cost = rev * d(random.uniform(0.92, 1.12))
                elif prof == "low_margin":
                    rev = rev * d(random.uniform(0.98, 1.08))
                    cost = rev * d(random.uniform(0.83, 0.93))
                elif prof == "spike":
                    if m == ms[-2]:
                        rev = rev * d(random.uniform(2.2, 3.3))
                    else:
                        rev = rev * d(random.uniform(0.98, 1.10))
                    cost = rev * d(random.uniform(0.60, 0.85))
                else:
                    rev = rev * d(random.uniform(0.98, 1.10))
                    cost = rev * d(random.uniform(0.60, 0.85))

                # clamp
                rev = max(rev, d(50_000_000))
                cost = max(cost, d(10_000_000))

                # KEY FIX: use tenant_id/shop_id to avoid context/scoped weirdness
                mp_mgr.update_or_create(
                    tenant_id=tenant.id,
                    shop_id=shop.id,
                    month=month_start(m),
                    defaults={
                        "revenue": rev.quantize(Decimal("0.01")),
                        "cost": cost.quantize(Decimal("0.01")),
                        "fixed_fee": fixed_fee,
                        "vat_percent": vat,
                        "sale_percent": sale_pct,
                    },
                )
                created_rows += 1

        self.stdout.write(
            self.style.SUCCESS(f"Seeded tenant={tenant.id} shops={len(all_shops)} rows={created_rows}")
        )
        self.stdout.write(
            self.style.SUCCESS("Login accounts: founder/admin/operator/client (pw: 123456)")
        )