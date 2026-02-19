from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from django.db import transaction
from django.utils import timezone


@dataclass
class ProvisionResult:
    company: str
    brand: str
    shop: str


class ProvisioningService:
    """
    Auto provision:
    Company -> Brand -> Shop -> ShopMember(owner)
    + AUTO: tạo MonthlyPerformance tháng hiện tại (0 data) để dashboard có hàng
    + AUTO: tạo finance snapshot tháng hiện tại (OPEN) nếu bật
    """

    @staticmethod
    def _month_start(d: Optional[date] = None) -> date:
        d = d or timezone.now().date()
        return date(d.year, d.month, 1)

    @staticmethod
    @transaction.atomic
    def provision_shop(
        *,
        company_name: str,
        brand_name: str,
        shop_name: str,
        owner_user=None,  # User instance hoặc None
        platform: Optional[str] = None,
        shop_code: Optional[str] = None,
        create_monthly_snapshot: bool = True,
        create_monthly_performance: bool = True,
        snapshot_month: Optional[date] = None,
    ) -> ProvisionResult:
        from apps.companies.models import Company
        from apps.brands.models import Brand
        from apps.shops.models import Shop, ShopMember

        company, _ = Company.objects.get_or_create(name=company_name)

        brand, _ = Brand.objects.get_or_create(
            company=company,
            name=brand_name,
        )

        shop, _ = Shop.objects.get_or_create(
            brand=brand,
            name=shop_name,
            defaults={
                "platform": platform,
                "code": shop_code,
                "is_active": True,
            },
        )

        # nếu shop đã tồn tại mà truyền platform/code mới -> update nhẹ
        need_update = False
        if platform is not None and shop.platform != platform:
            shop.platform = platform
            need_update = True
        if shop_code is not None and shop.code != shop_code:
            shop.code = shop_code
            need_update = True
        if need_update:
            shop.save(update_fields=["platform", "code"])

        # gán owner membership nếu có user
        if owner_user:
            ShopMember.objects.update_or_create(
                shop=shop,
                user=owner_user,
                defaults={"role": ShopMember.ROLE_OWNER, "is_active": True},
            )

        month = snapshot_month or ProvisioningService._month_start()

        # AUTO: tạo MonthlyPerformance tháng hiện tại (0 data) để dashboard có record
        if create_monthly_performance:
            from apps.performance.models import MonthlyPerformance

            # nếu model MonthlyPerformance của bạn dùng shop FK (đúng bản mới)
            MonthlyPerformance.objects.get_or_create(
                shop=shop,
                month=month,
                defaults={
                    "revenue": 0,
                    "cost": 0,
                    "fixed_fee": 0,
                    "vat_percent": 0,
                    "sale_percent": 0,
                },
            )

        # AUTO: tạo finance snapshot tháng hiện tại (OPEN) nếu bật
        if create_monthly_snapshot:
            from apps.finance.services import AgencyFinanceService

            AgencyFinanceService.calculate_or_update(month)

        return ProvisionResult(
            company=str(company),
            brand=f"{brand.name} ({company.name})",
            shop=f"{shop.name} ({brand.name})",
        )