from __future__ import annotations

from django.db import transaction
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.companies.models import Company
from apps.brands.models import Brand
from apps.shops.models import Shop
from apps.tenants.models import Tenant


class ShopCreateWorkspaceApi(APIView):
    def post(self, request):
        data = request.data or {}

        company_name = str(data.get("company_name") or "").strip()
        brand_name = str(data.get("brand_name") or "").strip()
        shop_name = str(data.get("name") or data.get("shop_name") or "").strip()
        platform = str(data.get("platform") or "").strip()
        industry_code = str(data.get("industry_code") or "default").strip() or "default"
        rule_version = str(data.get("rule_version") or "v1").strip() or "v1"
        description = str(data.get("description") or "").strip()

        if not company_name:
            return Response({"ok": False, "message": "Thiếu tên công ty"}, status=400)

        if not brand_name:
            return Response({"ok": False, "message": "Thiếu tên brand"}, status=400)

        if not shop_name:
            return Response({"ok": False, "message": "Thiếu tên shop"}, status=400)

        tenant_id = request.headers.get("X-Tenant-Id")
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        try:
            tenant = Tenant.objects.get(id=int(tenant_id))
        except Exception:
            return Response({"ok": False, "message": "Tenant không tồn tại"}, status=400)

        with transaction.atomic():
            company = Company.objects_all.create(
                tenant=tenant,
                agency=tenant.agency,
                name=company_name,
                max_clients=5,
                months_active=0,
                is_active=True,
            )

            brand = Brand.objects.create(
                tenant_id=tenant.id,
                company=company,
                name=brand_name,
            )

            shop = Shop.objects_all.create(
                tenant_id=tenant.id,
                brand_id=brand.id,
                name=shop_name,
                platform=platform or None,
                description=description or None,
                status=getattr(Shop, "STATUS_ACTIVE", "active"),
                industry_code=industry_code,
                rule_version=rule_version,
                is_active=True,
            )

        return Response(
            {
                "ok": True,
                "company": {
                    "id": company.id,
                    "name": company.name,
                },
                "brand": {
                    "id": brand.id,
                    "name": brand.name,
                },
                "shop": {
                    "id": shop.id,
                    "name": shop.name,
                },
            },
            status=201,
        )