# apps/core/management/commands/reset_demo.py
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.tenants.models import Tenant
from apps.companies.models import Company
from apps.brands.models import Brand
from apps.shops.models import Shop


class Command(BaseCommand):
    help = "Reset demo data by names (safe, idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="", help="Tenant name (optional). If provided, scope deletes to this tenant where possible.")
        parser.add_argument("--company", default="Height Media", help="Company name")
        parser.add_argument("--brand", default="Demo Brand", help="Brand name")
        parser.add_argument("--shop", default="Demo Shop", help="Shop name")
        parser.add_argument("--delete-company", action="store_true", help="Also delete company (default: keep)")
        parser.add_argument("--delete-tenant", action="store_true", help="Also delete tenant (dangerous)")

    @transaction.atomic
    def handle(self, *args, **opts):
        tenant_name = (opts["tenant"] or "").strip()
        company_name = (opts["company"] or "").strip()
        brand_name = (opts["brand"] or "").strip()
        shop_name = (opts["shop"] or "").strip()

        tenant = None
        if tenant_name:
            tenant = Tenant._base_manager.filter(name=tenant_name).first()
            if not tenant:
                self.stdout.write(self.style.WARNING(f"Tenant '{tenant_name}' not found. Continue without tenant scope."))

        # 1) delete shop
        shop_qs = Shop._base_manager.filter(name=shop_name)
        if tenant:
            shop_qs = shop_qs.filter(tenant_id=tenant.id)
        shop_count = shop_qs.count()
        shop_qs.delete()

        # 2) delete brand
        brand_qs = Brand._base_manager.filter(name=brand_name)
        if tenant and hasattr(Brand, "company_id"):
            # Brand thường scope theo company, không có tenant trực tiếp nên để tự nhiên
            pass
        brand_count = brand_qs.count()
        brand_qs.delete()

        # 3) delete company (optional)
        company_count = 0
        if opts["delete_company"]:
            company_qs = Company._base_manager.filter(name=company_name)
            if tenant:
                company_qs = company_qs.filter(tenant_id=tenant.id)
            company_count = company_qs.count()
            company_qs.delete()

        # 4) delete tenant (optional - dangerous)
        tenant_deleted = False
        if opts["delete_tenant"] and tenant:
            tenant.delete()
            tenant_deleted = True

        self.stdout.write(self.style.SUCCESS(
            f"reset_demo OK: deleted shops={shop_count}, brands={brand_count}, companies={company_count}, tenant_deleted={tenant_deleted}"
        ))
        