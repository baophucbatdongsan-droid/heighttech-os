# scripts/seed_demo.py
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.core.tenant_context import set_current_tenant
from apps.tenants.models import Tenant
from apps.companies.models import Company
from apps.clients.models import Client


def run(tenant_id: int = 1, user_id: int = 1):
    """
    Seed demo data for 1 tenant:
    - Company (1)
    - Clients (>=1)
    - Brand (1)
    - Shops: 2 / client
    - Projects: 2 / shop
    - WorkItems: 3 / project
    """

    # -------------------------
    # Tenant context
    # -------------------------
    t = Tenant.objects.get(id=tenant_id)
    set_current_tenant(t)

    User = get_user_model()
    u = User.objects.get(id=user_id)

    created = {
        "company": 0,
        "clients": 0,
        "brands": 0,
        "shops": 0,
        "projects": 0,
        "workitems": 0,
    }

    # -------------------------
    # Company
    # -------------------------
    company = Company.objects.first()
    if not company:
        company = Company._base_manager.create(
            tenant=t,
            agency=getattr(t, "agency", None),
            name="HeightTech Demo Company",
            max_clients=50,
            months_active=0,
            is_active=True,
        )
        created["company"] += 1

    # -------------------------
    # Clients
    # -------------------------
    clients = list(Client.objects.filter(company=company).order_by("id"))
    if not clients:
        client = Client.objects.create(
            company=company,
            brand_name="Client Demo 01",
            contract_start=date.today(),
            contract_end=date.today() + timedelta(days=365),
            fixed_fee=Decimal("8000000"),
            percent_fee=Decimal("3.5"),
            account_manager=u,
            operator=u,
        )
        clients = [client]
        created["clients"] += 1

    # -------------------------
    # Lazy imports
    # -------------------------
    from apps.brands.models import Brand
    from apps.shops.models import Shop
    from apps.projects.models import Project, ProjectShop
    from apps.work.models import WorkItem

    # -------------------------
    # Brand
    # -------------------------
    brand, brand_created = Brand._base_manager.get_or_create(
        tenant_id=t.id,
        company_id=company.id,
        name="HeightTech",
        defaults={"is_active": True},
    )
    if brand_created:
        created["brands"] += 1

    # -------------------------
    # Seed transactional
    # -------------------------
    with transaction.atomic():

        for c in clients:

            # 2 shops / client
            for sidx in range(1, 3):
                shop_code = f"C{c.id:03d}-S{sidx:02d}"

                shop, shop_created = Shop.objects.get_or_create(
                    tenant_id=t.id,
                    code=shop_code,
                    defaults=dict(
                        brand=brand,
                        name=f"Shop {shop_code}",
                        platform="tiktok",
                        description=f"Seed demo shop for client {c.id}",
                        status="active",
                        industry_code="general",
                        rule_version="v2026_02",
                        started_at=timezone.now(),   # ✅ timezone-safe
                        is_active=True,
                    ),
                )

                if shop_created:
                    created["shops"] += 1

                # 2 projects / shop
                for pidx in range(1, 3):
                    project_name = f"Project {shop_code}-{pidx:02d}"

                    project, p_created = Project.objects.get_or_create(
                        tenant_id=t.id,
                        company_id=company.id,
                        name=project_name,
                        defaults=dict(
                            status="active",
                            owner_id=u.id,
                            started_at=timezone.now(),   # ✅ fix warning
                        ),
                    )

                    if p_created:
                        created["projects"] += 1

                    ProjectShop.objects.get_or_create(
                        project=project,
                        shop=shop,
                        defaults=dict(status="active"),
                    )

                    # 3 workitems / project
                    for widx in range(1, 4):
                        wi_title = f"Task {project_name}-{widx:02d}"

                        wi, wi_created = WorkItem.objects.get_or_create(
                            tenant_id=t.id,
                            project=project,
                            title=wi_title,
                            defaults=dict(
                                status="todo",
                                priority=2,
                                created_by=u,
                                assignee=u,
                            ),
                        )

                        if wi_created:
                            created["workitems"] += 1

    # -------------------------
    # Summary
    # -------------------------
    print("===================================")
    print("✅ Seed done for tenant:", t.id, t.name)
    print("Company:", company.id, company.name)
    print("Brand:", brand.id, brand.name, "company_id=", brand.company_id)
    print("Clients:", [(x.id, x.brand_name) for x in clients])
    print("Created:", created)
    print("===================================")