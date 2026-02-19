from __future__ import annotations

from datetime import date
from typing import Optional

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.shops.models import Shop, ShopMember


def _month_first_day(d: date) -> date:
    return d.replace(day=1)


def _add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return date(y, m, 1)


def _seed_monthly_performance(shop: Shop, months_back: int = 11) -> int:
    """
    Seed MonthlyPerformance for shop:
    - current month + months_back months before => total months_back+1 rows
    """
    from apps.performance.models import MonthlyPerformance  # local import

    base = _month_first_day(timezone.localdate())
    months = [_add_months(base, -i) for i in range(0, months_back + 1)]

    # OPTIONAL defaults theo field tồn tại (tránh crash nếu model khác)
    field_names = {f.name for f in MonthlyPerformance._meta.get_fields()}

    created_count = 0
    for m in months:
        defaults = {"revenue": 0}

        if "fixed_fee" in field_names:
            defaults["fixed_fee"] = 0
        if "vat_percent" in field_names:
            defaults["vat_percent"] = 10
        if "sale_percent" in field_names:
            defaults["sale_percent"] = 0

        obj, created = MonthlyPerformance.objects.get_or_create(
            shop=shop,
            month=m,
            defaults=defaults,
        )
        if created:
            created_count += 1

    return created_count


class Command(BaseCommand):
    help = "Provision Company + Brand + Shop + Owner + seed MonthlyPerformance (12 months rolling)."

    def add_arguments(self, parser):
        parser.add_argument("--company", required=True, help='Company name, e.g. "Height Tech"')
        parser.add_argument("--brand", required=True, help='Brand name, e.g. "Brand A"')
        parser.add_argument("--shop", required=True, help='Shop name, e.g. "Shop 01"')

        parser.add_argument(
            "--owner",
            required=True,
            help="Owner username or email. If not exists, will auto-create user.",
        )
        parser.add_argument("--password", default=None, help="Optional password for auto-created owner user.")
        parser.add_argument("--platform", default=None, help="Optional platform: Shopee/Lazada/Tiktok...")
        parser.add_argument("--code", default=None, help="Optional shop slug code")
        parser.add_argument("--inactive", action="store_true", help="Create shop inactive")
        parser.add_argument(
            "--seed-months",
            type=int,
            default=12,
            help="How many months to seed (default 12).",
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        company_name: str = opts["company"].strip()
        brand_name: str = opts["brand"].strip()
        shop_name: str = opts["shop"].strip()
        owner_key: str = opts["owner"].strip()
        password: Optional[str] = opts.get("password")
        platform: Optional[str] = opts.get("platform")
        code: Optional[str] = opts.get("code")
        inactive: bool = bool(opts.get("inactive"))
        seed_months: int = int(opts.get("seed_months") or 12)

        if seed_months < 1:
            raise CommandError("--seed-months must be >= 1")

        # 1) owner user
        User = get_user_model()
        owner = (
            User.objects.filter(username=owner_key).first()
            or User.objects.filter(email=owner_key).first()
        )

        created_user = False
        generated_password = None
        if not owner:
            # auto create user
            if "@" in owner_key:
                username = owner_key.split("@")[0]
                email = owner_key
            else:
                username = owner_key
                email = ""

            if not password:
                generated_password = User.objects.make_random_password(length=14)
                password = generated_password

            owner = User.objects.create_user(username=username, email=email, password=password)
            created_user = True

        # 2) company
        from apps.companies.models import Company  # local import
        company, company_created = Company.objects.get_or_create(name=company_name)

        # 3) brand
        from apps.brands.models import Brand  # local import

        # Nếu Brand model của bạn có FK company => dùng get_or_create theo company+name
        brand_kwargs = {"name": brand_name}
        if "company" in {f.name for f in Brand._meta.get_fields()}:
            brand_kwargs["company"] = company

        brand, brand_created = Brand.objects.get_or_create(**brand_kwargs)

        # 4) shop
        shop_defaults = {
            "platform": platform,
            "code": code,
            "is_active": not inactive,
        }
        shop, shop_created = Shop.objects.get_or_create(
            brand=brand,
            name=shop_name,
            defaults=shop_defaults,
        )

        # nếu tồn tại shop rồi, vẫn update platform/code/is_active nếu user có truyền
        if not shop_created:
            changed = False
            if platform is not None and shop.platform != platform:
                shop.platform = platform
                changed = True
            if code is not None and shop.code != code:
                shop.code = code
                changed = True
            if inactive is not None and shop.is_active == inactive:
                shop.is_active = not inactive
                changed = True
            if changed:
                shop.save()

        # 5) ShopMember OWNER
        ShopMember.objects.update_or_create(
            shop=shop,
            user=owner,
            defaults={"role": ShopMember.ROLE_OWNER, "is_active": True},
        )

        # 6) seed MonthlyPerformance (12 months rolling)
        created_rows = _seed_monthly_performance(shop=shop, months_back=seed_months - 1)

        # output
        self.stdout.write("PROVISION VERSION: V2 FULL")
        self.stdout.write(self.style.SUCCESS("✅ PROVISION DONE"))
        self.stdout.write(f"- Company: {company.name} ({'created' if company_created else 'exists'})")
        self.stdout.write(f"- Brand: {brand.name} ({'created' if brand_created else 'exists'})")
        self.stdout.write(f"- Shop: {shop.name} ({'created' if shop_created else 'exists'})")
        self.stdout.write(f"- Owner: {owner.username} ({'created' if created_user else 'exists'})")
        if created_user and generated_password:
            self.stdout.write(self.style.WARNING(f"  ↳ Generated password: {generated_password}"))
        self.stdout.write(f"- Seed MonthlyPerformance rows created: {created_rows}")