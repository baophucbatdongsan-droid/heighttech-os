from __future__ import annotations

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.authtoken.models import Token


class Command(BaseCommand):
    help = "Seed dev data: tenant/company/brand/shop + admin/client tokens + memberships"

    def add_arguments(self, parser):
        parser.add_argument("--tenant-id", type=int, default=1)
        parser.add_argument("--company-id", type=int, default=1)
        parser.add_argument("--brand-id", type=int, default=1)
        parser.add_argument("--shop-id", type=int, default=1)
        parser.add_argument("--admin", type=str, default="admin")
        parser.add_argument("--client", type=str, default="client1")
        parser.add_argument("--password", type=str, default="123456")

    def _mgr(self, Model):
        return getattr(Model, "objects_all", Model.objects)

    @transaction.atomic
    def handle(self, *args, **opts):
        # IMPORT MODELS INSIDE handle: tránh lỗi import sớm + tránh lộ biến top-level làm bạn nhầm
        from apps.tenants.models import Tenant
        from apps.companies.models import Company
        from apps.accounts.models import Membership
        from apps.brands.models import Brand
        from apps.shops.models import Shop

        tenant_id = opts["tenant_id"]
        company_id = opts["company_id"]
        brand_id = opts["brand_id"]
        shop_id = opts["shop_id"]
        admin_username = opts["admin"]
        client_username = opts["client"]
        password = opts["password"]

        TenantM = self._mgr(Tenant)
        CompanyM = self._mgr(Company)
        BrandM = self._mgr(Brand)
        ShopM = self._mgr(Shop)

        # 1) Tenant
        tenant, _ = TenantM.get_or_create(id=tenant_id, defaults={"name": f"Tenant {tenant_id}"})

        # 2) Company
        company = CompanyM.filter(id=company_id).first()
        if not company:
            company = CompanyM.create(id=company_id, tenant_id=tenant.id, name=f"Company {company_id}")
        else:
            if getattr(company, "tenant_id", None) != tenant.id:
                company.tenant_id = tenant.id
                company.save()

        # 3) Brand
        brand = BrandM.filter(id=brand_id).first()
        if not brand:
            brand = BrandM.create(id=brand_id, name=f"Brand {brand_id}", company_id=company.id)
        else:
            if getattr(brand, "company_id", None) != company.id:
                brand.company_id = company.id
                brand.save()

        # 4) Shop
        shop = ShopM.filter(id=shop_id).first()
        if not shop:
            kwargs = {"id": shop_id, "name": f"Shop {shop_id}", "brand_id": brand.id}
            if any(f.name == "is_active" for f in Shop._meta.fields):
                kwargs["is_active"] = True
            shop = ShopM.create(**kwargs)
        else:
            if getattr(shop, "brand_id", None) != brand.id:
                shop.brand_id = brand.id
                shop.save()

        # 5) Users + tokens
        User = get_user_model()

        admin, created = User.objects.get_or_create(
            username=admin_username,
            defaults={"email": "admin@test.com", "is_staff": True, "is_superuser": True},
        )
        if created:
            admin.set_password(password)
            admin.save()
        Token.objects.filter(user=admin).delete()
        admin_token = Token.objects.create(user=admin)

        client, created = User.objects.get_or_create(
            username=client_username,
            defaults={"email": "client@test.com", "is_staff": False, "is_superuser": False},
        )
        if created:
            client.set_password(password)
            client.save()
        Token.objects.filter(user=client).delete()
        client_token = Token.objects.create(user=client)

        # 6) Membership
        m, _ = Membership.objects.get_or_create(
            user=client,
            company_id=company.id,
            defaults={"is_active": True, "role": "owner"},
        )
        m.is_active = True
        m.role = m.role or "owner"
        m.save()

        # 7) ShopMember (nếu có)
        shop_member_msg = "shop_member=SKIP(no model)"
        try:
            from apps.shops.models import ShopMember

            sm, _ = ShopMember.objects.get_or_create(
                user=client,
                shop_id=shop.id,
                defaults={"is_active": True, "role": "member"},
            )
            sm.is_active = True
            sm.save()
            shop_member_msg = f"shop_member={sm.id}"
        except Exception:
            pass

        self.stdout.write(self.style.SUCCESS("=== SEED OK ==="))
        self.stdout.write(f"tenant={tenant.id}")
        self.stdout.write(f"company={company.id} tenant_id={company.tenant_id}")
        self.stdout.write(f"brand={brand.id} company_id={getattr(brand,'company_id',None)}")
        self.stdout.write(f"shop={shop.id} brand_id={getattr(shop,'brand_id',None)}")
        self.stdout.write(f"admin={admin.username} token={admin_token.key}")
        self.stdout.write(f"client={client.username} token={client_token.key}")
        self.stdout.write(f"membership={m.id} role={m.role} active={m.is_active}")
        self.stdout.write(shop_member_msg)