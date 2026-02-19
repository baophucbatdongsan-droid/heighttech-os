# apps/finance/services.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone


# =====================================================
# CONSTANTS
# =====================================================

# GMV fee: bạn xác nhận coi như gộp VAT+TNDN tổng 30% => còn 70%
GMV_AFTER_TAX_RATE = Decimal("0.70")

# BONUS RULES (team share trên phần GMV fee after tax)
BONUS_BASE = Decimal("20")
BONUS_GROWTH_15 = Decimal("5")
BONUS_GROWTH_25 = Decimal("10")
BONUS_KEEP_6M = Decimal("2")
MAX_BONUS = Decimal("32")  # 20 + 10 + 2


# =====================================================
# HELPERS
# =====================================================

def d(value) -> Decimal:
    return Decimal(str(value or "0"))


def q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# =====================================================
# COMMISSION ENGINE (1 performance / 1 shop)
# =====================================================

@dataclass
class CommissionSummary:
    gmv_rate: Decimal
    gmv_fee_gross: Decimal
    gmv_fee_after_tax: Decimal

    team_bonus_percent: Decimal
    team_bonus_amount: Decimal

    fixed_fee_net: Decimal
    fixed_fee_net_after_tax: Decimal

    sale_commission: Decimal

    company_net_profit: Decimal


class CommissionEngine:
    """
    Engine tính tiền cho 1 shop/tháng dựa trên:
    - gmv (nên truyền GMV NET = gross - hoàn/huỷ)
    - fixed_fee
    - growth_percent
    - months_active
    - vat_percent cho fixed fee (0/8/10 tuỳ) -> để trừ VAT ra net
    - sale_percent (3-6%) áp trên fixed fee net after tax
    """

    def __init__(
        self,
        gmv: Decimal,
        fixed_fee: Decimal,
        growth_percent: Decimal,
        months_active: int,
        vat_percent: Decimal = Decimal("10"),
        sale_percent: Decimal = Decimal("0"),
    ):
        self.gmv = d(gmv)
        self.fixed_fee = d(fixed_fee)
        self.growth_percent = d(growth_percent)
        self.months_active = int(months_active or 0)
        self.vat_percent = d(vat_percent)
        self.sale_percent = d(sale_percent)

    # =========================================
    # GMV SERVICE RATE (THEO TẦNG)
    # =========================================
    def get_gmv_rate(self) -> Decimal:
        """
        Rule:
        - GMV < 1B: 4%
        - 1B - 2B: 3.5%
        - > 2B: 3%
        """
        if self.gmv < Decimal("1000000000"):
            return Decimal("0.04")
        if self.gmv < Decimal("2000000000"):
            return Decimal("0.035")
        return Decimal("0.03")

    # =========================================
    # TEAM BONUS %
    # =========================================
    def get_team_bonus_percent(self) -> Decimal:
        bonus = BONUS_BASE

        if self.growth_percent >= Decimal("25"):
            bonus += BONUS_GROWTH_25
        elif self.growth_percent >= Decimal("15"):
            bonus += BONUS_GROWTH_15

        if self.months_active >= 6:
            bonus += BONUS_KEEP_6M

        if bonus > MAX_BONUS:
            bonus = MAX_BONUS

        return bonus

    # =========================================
    # MAIN SUMMARY
    # =========================================
    def summary(self) -> CommissionSummary:
        gmv_rate = self.get_gmv_rate()
        gmv_fee_gross = self.gmv * gmv_rate
        gmv_fee_after_tax = gmv_fee_gross * GMV_AFTER_TAX_RATE

        team_bonus_percent = self.get_team_bonus_percent()
        team_bonus_amount = gmv_fee_after_tax * (team_bonus_percent / Decimal("100"))

        # Fixed fee net (trừ VAT)
        fixed_fee_net = self.fixed_fee * (Decimal("1") - (self.vat_percent / Decimal("100")))
        fixed_fee_net_after_tax = fixed_fee_net * GMV_AFTER_TAX_RATE

        sale_commission = fixed_fee_net_after_tax * (self.sale_percent / Decimal("100"))

        company_net_profit = (
            gmv_fee_after_tax
            + fixed_fee_net_after_tax
            - team_bonus_amount
            - sale_commission
        )

        return CommissionSummary(
            gmv_rate=q2(gmv_rate),
            gmv_fee_gross=q2(gmv_fee_gross),
            gmv_fee_after_tax=q2(gmv_fee_after_tax),

            team_bonus_percent=q2(team_bonus_percent),
            team_bonus_amount=q2(team_bonus_amount),

            fixed_fee_net=q2(fixed_fee_net),
            fixed_fee_net_after_tax=q2(fixed_fee_net_after_tax),

            sale_commission=q2(sale_commission),

            company_net_profit=q2(company_net_profit),
        )


# =====================================================
# AGENCY FINANCE SERVICE (snapshot / lock / finalize)
# =====================================================

class AgencyFinanceService:
    """
    Enterprise layer:
    - Tổng hợp số liệu theo tháng vào AgencyMonthlyFinance (snapshot)
    - OPEN: được phép recalc/update
    - LOCKED/FINALIZED: freeze, không update
    """

    @staticmethod
    def _get_or_create_snapshot(month):
        from apps.finance.models import AgencyMonthlyFinance  # local import tránh circular
        obj, _ = AgencyMonthlyFinance.objects.get_or_create(month=month)
        return obj

    @staticmethod
    def calculate_totals(month) -> Dict[str, Decimal]:
        """
        Tổng hợp từ MonthlyPerformance.

        YÊU CẦU MonthlyPerformance đã có các field:
        - gmv_fee_after_tax
        - fixed_fee_net
        - fixed_fee_net_after_tax
        - sale_commission
        - bonus_amount
        """
        from apps.performance.models import MonthlyPerformance

        qs = MonthlyPerformance.objects.filter(month=month)

        total_gmv_fee = qs.aggregate(total=Sum("gmv_fee_after_tax"))["total"] or Decimal("0")
        total_fixed_fee_net = qs.aggregate(total=Sum("fixed_fee_net"))["total"] or Decimal("0")
        total_fixed_fee_net_after_tax = qs.aggregate(total=Sum("fixed_fee_net_after_tax"))["total"] or Decimal("0")

        total_sale = qs.aggregate(total=Sum("sale_commission"))["total"] or Decimal("0")
        total_team = qs.aggregate(total=Sum("bonus_amount"))["total"] or Decimal("0")

        operating_cost = Decimal("0")

        net = (
            d(total_gmv_fee)
            + d(total_fixed_fee_net_after_tax)
            - d(total_sale)
            - d(total_team)
            - d(operating_cost)
        )

        return {
            "total_gmv_fee_after_tax": q2(d(total_gmv_fee)),
            "total_fixed_fee_net": q2(d(total_fixed_fee_net)),
            "total_sale_commission": q2(d(total_sale)),
            "total_team_bonus": q2(d(total_team)),
            "total_operating_cost": q2(d(operating_cost)),
            "agency_net_profit": q2(net),
        }

    @staticmethod
    @transaction.atomic
    def calculate_or_update(month):
        obj = AgencyFinanceService._get_or_create_snapshot(month)

        if not obj.can_edit():
            return obj

        totals = AgencyFinanceService.calculate_totals(month)
        for k, v in totals.items():
            setattr(obj, k, v)

        obj.calculated_at = timezone.now()
        obj.save(update_fields=[
            "total_gmv_fee_after_tax",
            "total_fixed_fee_net",
            "total_sale_commission",
            "total_team_bonus",
            "total_operating_cost",
            "agency_net_profit",
            "calculated_at",
            "updated_at",
        ])
        return obj

    @staticmethod
    @transaction.atomic
    def lock_month(month):
        obj = AgencyFinanceService.calculate_or_update(month)
        obj.lock()
        return obj

    @staticmethod
    @transaction.atomic
    def finalize_month(month):
        obj = AgencyFinanceService._get_or_create_snapshot(month)

        if obj.can_edit():
            obj = AgencyFinanceService.calculate_or_update(month)

        obj.finalize()
        return obj

    @staticmethod
    @transaction.atomic
    def reopen_month(month):
        from apps.finance.models import AgencyMonthlyFinance
        obj = AgencyFinanceService._get_or_create_snapshot(month)

        obj.status = AgencyMonthlyFinance.STATUS_OPEN
        obj.locked_at = None
        obj.finalized_at = None
        obj.save(update_fields=["status", "locked_at", "finalized_at", "updated_at"])
        return obj