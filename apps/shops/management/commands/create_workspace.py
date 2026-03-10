from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.shops.services_workspace import create_shop_workspace


class Command(BaseCommand):
    help = "Tạo Tenant + Company + Brand + Shop workspace"

    def add_arguments(self, parser):
        parser.add_argument("--tenant-name", required=True)
        parser.add_argument("--company-name", required=True)
        parser.add_argument("--brand-name", required=True)
        parser.add_argument("--shop-name", required=True)
        parser.add_argument("--platform", default="shopee")
        parser.add_argument("--industry-code", default="default")
        parser.add_argument("--rule-version", default="v1")

    def handle(self, *args, **options):
        ws = create_shop_workspace(
            tenant_name=options["tenant_name"],
            company_name=options["company_name"],
            brand_name=options["brand_name"],
            shop_name=options["shop_name"],
            platform=options["platform"],
            industry_code=options["industry_code"],
            rule_version=options["rule_version"],
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Tạo xong workspace | "
                f"tenant={ws.tenant.id} "
                f"company={ws.company.id} "
                f"brand={ws.brand.id} "
                f"shop={ws.shop.id}"
            )
        )