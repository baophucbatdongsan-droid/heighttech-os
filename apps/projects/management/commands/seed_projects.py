from __future__ import annotations

import random
import string
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.tenants.models import Tenant
from apps.companies.models import Company
from apps.brands.models import Brand
from apps.shops.models import Shop
from apps.projects.models import Project, ProjectShop


def _rand_suffix(n: int = 6) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))


def _mgr(model_cls):
    """
    Seed phải dùng manager KHÔNG filter tenant.
    Ưu tiên objects_all nếu có, fallback về _base_manager.
    """
    return getattr(model_cls, "objects_all", model_cls._base_manager)


class Command(BaseCommand):
    help = "Seed fake data for Projects dashboard (Companies + Brands + Shops + Projects + ProjectShop). Safe to run multiple times."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, default=None)
        parser.add_argument("--companies", type=int, default=2)
        parser.add_argument("--brands-per-company", type=int, default=3)
        parser.add_argument("--projects", type=int, default=25)
        parser.add_argument("--shops", type=int, default=60)
        parser.add_argument("--links-min", type=int, default=1)
        parser.add_argument("--links-max", type=int, default=4)

    def handle(self, *args, **opts):
        tenant_id = opts["tenant"]
        n_companies = int(opts["companies"])
        brands_per_company = int(opts["brands_per_company"])
        n_projects = int(opts["projects"])
        n_shops = int(opts["shops"])
        links_min = int(opts["links_min"])
        links_max = int(opts["links_max"])

        TenantMgr = _mgr(Tenant)
        CompanyMgr = _mgr(Company)
        BrandMgr = _mgr(Brand)
        ShopMgr = _mgr(Shop)
        ProjectMgr = _mgr(Project)
        ProjectShopMgr = _mgr(ProjectShop)

        # =========================
        # 0) Tenant
        # =========================
        if tenant_id:
            tenant = TenantMgr.get(id=tenant_id)
        else:
            tenant = TenantMgr.order_by("id").first()

        if not tenant:
            self.stdout.write(self.style.ERROR("No tenant found. Create Tenant first."))
            return

        # =========================
        # 1) Companies (unique tenant+name safe)
        # =========================
        companies = list(CompanyMgr.filter(tenant_id=tenant.id)[:n_companies])

        while len(companies) < n_companies:
            base_name = f"Company {len(companies) + 1}"
            c, created = CompanyMgr.get_or_create(
                tenant_id=tenant.id,
                name=base_name,
                defaults={"is_active": True},
            )
            if not created:
                # tránh unique clash
                unique_name = f"{base_name} - {_rand_suffix()}"
                c, _ = CompanyMgr.get_or_create(
                    tenant_id=tenant.id,
                    name=unique_name,
                    defaults={"is_active": True},
                )
            companies.append(c)

        # =========================
        # 2) Brands (brand.company_id NOT NULL)
        # mỗi company có brands_per_company brand
        # =========================
        brands: list[Brand] = []
        for c in companies:
            existing = list(BrandMgr.filter(company_id=c.id)[:brands_per_company])
            brands.extend(existing)

            while len(existing) < brands_per_company:
                base_name = f"Brand {c.id}-{len(existing) + 1}"
                b, created = BrandMgr.get_or_create(
                    tenant_id=tenant.id,
                    company_id=c.id,
                    name=base_name,
                    defaults={"is_active": True},
                )
                if not created:
                    unique_name = f"{base_name} - {_rand_suffix()}"
                    b, _ = BrandMgr.get_or_create(
                        tenant_id=tenant.id,
                        company_id=c.id,
                        name=unique_name,
                        defaults={"is_active": True},
                    )
                existing.append(b)
                brands.append(b)

        if not brands:
            self.stdout.write(self.style.ERROR("No brands created. Check Brand model required fields."))
            return

        # =========================
        # 3) Shops (shop.brand_id NOT NULL)
        # =========================
        shops = list(ShopMgr.filter(tenant_id=tenant.id)[:n_shops])

        while len(shops) < n_shops:
            brand = random.choice(brands)
            base_name = f"Shop {len(shops) + 1}"
            s, created = ShopMgr.get_or_create(
                tenant_id=tenant.id,
                name=base_name,
                defaults={
                    "brand_id": brand.id,
                    "is_active": True,
                },
            )
            if not created:
                unique_name = f"{base_name} - {_rand_suffix()}"
                s, _ = ShopMgr.get_or_create(
                    tenant_id=tenant.id,
                    name=unique_name,
                    defaults={
                        "brand_id": brand.id,
                        "is_active": True,
                    },
                )
            shops.append(s)

        # =========================
        # 4) Projects + ProjectShop links
        # =========================
        types = [Project.TYPE_SHOP_OPERATION, Project.TYPE_BUILD_CHANNEL, Project.TYPE_BOOKING]
        statuses = [Project.STATUS_ACTIVE, Project.STATUS_PAUSED, Project.STATUS_DONE]

        created_projects = 0
        created_links = 0

        for i in range(n_projects):
            company = random.choice(companies)

            p = ProjectMgr.create(
                tenant_id=tenant.id,
                company_id=company.id,
                name=f"Project {i + 1} - {company.name} - {_rand_suffix(4)}",
                type=random.choice(types),
                status=random.choice(statuses),
                progress_percent=random.randint(0, 100),
                health_score=random.randint(40, 100),
                last_activity_at=timezone.now() - timedelta(days=random.randint(0, 20)),
                started_at=timezone.now() - timedelta(days=random.randint(0, 60)),
            )
            created_projects += 1

            k = random.randint(links_min, links_max)
            for sh in random.sample(shops, k=min(k, len(shops))):
                _, link_created = ProjectShopMgr.get_or_create(
                    tenant_id=tenant.id,
                    project_id=p.id,
                    shop_id=sh.id,
                    defaults={
                        "role": random.choice(
                            [ProjectShop.ROLE_OPERATION, ProjectShop.ROLE_BUILD, ProjectShop.ROLE_BOOKING]
                        ),
                        "status": random.choice(
                            [
                                ProjectShop.STATUS_ACTIVE,
                                ProjectShop.STATUS_PAUSED,
                                ProjectShop.STATUS_DONE,
                                ProjectShop.STATUS_INACTIVE,
                            ]
                        ),
                        "started_at": timezone.now() - timedelta(days=random.randint(0, 60)),
                    },
                )
                if link_created:
                    created_links += 1

        self.stdout.write(
            self.style.SUCCESS(
                "✅ Seed done: "
                f"tenant={tenant.id} "
                f"companies={len(companies)} "
                f"brands={len(brands)} "
                f"shops={len(shops)} "
                f"projects_created={created_projects} "
                f"links_created={created_links}"
            )
        )