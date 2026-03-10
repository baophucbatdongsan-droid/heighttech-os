from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from django.db import transaction

from apps.tenants.models import Tenant
from apps.companies.models import Company
from apps.brands.models import Brand
from apps.shops.models import Shop


def _slugify(value: str) -> str:
    value = str(value or "").strip().lower()
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "item"


def _unique_shop_code(base: str) -> str:
    code = _slugify(base)
    final_code = code
    idx = 1

    while Shop.objects_all.filter(code=final_code).exists():
        idx += 1
        final_code = f"{code}-{idx}"

    return final_code


@dataclass(frozen=True)
class ShopWorkspaceResult:
    tenant: Tenant
    company: Company
    brand: Brand
    shop: Shop


@transaction.atomic
def create_shop_workspace(
    *,
    owner_user=None,
    tenant_name: str,
    company_name: str,
    brand_name: str,
    shop_name: str,
    platform: str = "shopee",
    industry_code: str = "default",
    rule_version: str = "v1",
):
    tenant_name = str(tenant_name or "").strip()
    company_name = str(company_name or "").strip()
    brand_name = str(brand_name or "").strip()
    shop_name = str(shop_name or "").strip()
    platform = str(platform or "shopee").strip().lower()
    industry_code = str(industry_code or "default").strip()
    rule_version = str(rule_version or "v1").strip()

    if not tenant_name:
        raise ValueError("Thiếu tenant_name")
    if not company_name:
        raise ValueError("Thiếu company_name")
    if not brand_name:
        raise ValueError("Thiếu brand_name")
    if not shop_name:
        raise ValueError("Thiếu shop_name")

    tenant = Tenant.objects.create(
        name=tenant_name,
    )

    company_defaults = {
        "name": company_name,
    }

    if hasattr(Company, "code"):
        company_defaults["code"] = _slugify(company_name)

    company = Company.objects.create(
        tenant=tenant,
        **company_defaults,
    )

    brand_defaults = {
        "tenant": tenant,
        "company": company,
        "name": brand_name,
    }

    if hasattr(Brand, "code"):
        brand_defaults["code"] = _slugify(brand_name)

    brand = Brand.objects.create(**brand_defaults)

    shop_defaults = {
        "tenant": tenant,
        "brand": brand,
        "name": shop_name,
        "code": _unique_shop_code(shop_name),
    }

    if hasattr(Shop, "platform"):
        shop_defaults["platform"] = platform

    if hasattr(Shop, "status"):
        shop_defaults["status"] = "active"

    if hasattr(Shop, "is_active"):
        shop_defaults["is_active"] = True

    if hasattr(Shop, "industry_code"):
        shop_defaults["industry_code"] = industry_code

    if hasattr(Shop, "rule_version"):
        shop_defaults["rule_version"] = rule_version

    shop = Shop.objects.create(**shop_defaults)

    # gắn owner nếu hệ có membership/link model thì xử sau
    # tạm thời chỉ trả kết quả, chưa ép logic membership để tránh crash beta

    return ShopWorkspaceResult(
        tenant=tenant,
        company=company,
        brand=brand,
        shop=shop,
    )