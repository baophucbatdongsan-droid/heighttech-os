from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.core.provisioning import ProvisioningService


class Command(BaseCommand):
    help = "Auto provision Company -> Brand -> Shop -> ShopMember(owner) + optional month snapshot/performance"

    def add_arguments(self, parser):
        parser.add_argument("--company", required=True)
        parser.add_argument("--brand", required=True)
        parser.add_argument("--shop", required=True)
        parser.add_argument("--owner", required=False, help="username/email của owner user")
        parser.add_argument("--platform", required=False)
        parser.add_argument("--code", required=False)
        parser.add_argument("--no-snapshot", action="store_true")
        parser.add_argument("--no-performance", action="store_true")

    def handle(self, *args, **options):
        company = options["company"]
        brand = options["brand"]
        shop = options["shop"]
        owner = options.get("owner")
        platform = options.get("platform")
        code = options.get("code")
        no_snapshot = options.get("no_snapshot", False)
        no_performance = options.get("no_performance", False)

        owner_user = None
        if owner:
            User = get_user_model()
            owner_user = (
                User.objects.filter(username=owner).first()
                or User.objects.filter(email=owner).first()
            )
            if not owner_user:
                raise CommandError(f"Owner user '{owner}' không tồn tại (username/email).")

        res = ProvisioningService.provision_shop(
            company_name=company,
            brand_name=brand,
            shop_name=shop,
            owner_user=owner_user,
            platform=platform,
            shop_code=code,
            create_monthly_snapshot=(not no_snapshot),
            create_monthly_performance=(not no_performance),
        )

        self.stdout.write(self.style.SUCCESS("✅ Provision OK"))
        self.stdout.write(f"Company: {res.company}")
        self.stdout.write(f"Brand:   {res.brand}")
        self.stdout.write(f"Shop:    {res.shop}")