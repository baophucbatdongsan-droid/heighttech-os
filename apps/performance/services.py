# apps/performance/services.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.db.models import Sum
from django.utils import timezone

from apps.performance.models import MonthlyPerformance
from apps.rules.resolver import get_engine
from apps.rules.types import CommissionInput, EngineContext


def d(v) -> Decimal:
    return Decimal(str(v or "0"))


def q2(v: Decimal) -> Decimal:
    return d(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class CommissionSnapshot:
    # percent numbers, e.g. 4.00 means 4%
    service_percent: Decimal

    percent_fee_amount: Decimal
    gmv_fee_after_tax: Decimal

    bonus_percent: Decimal
    bonus_amount: Decimal

    fixed_fee_net: Decimal
    fixed_fee_net_after_tax: Decimal

    sale_commission: Decimal

    company_net_profit: Decimal


class PerformanceCalculator:
    """
    SINGLE SOURCE OF TRUTH for MonthlyPerformance calculations.

    - Reads inputs from MonthlyPerformance: revenue, cost, fixed_fee, vat_percent, sale_percent, growth_percent
    - Uses Rule Engine (apps.rules) to compute GMV fee & team bonus
    - Fills ALL NOT NULL numeric fields to satisfy DB constraints
    """

    def __init__(self, perf: MonthlyPerformance, months_active: Optional[int] = None):
        self.p = perf
        self.months_active = int(months_active or 0)

    def _ctx(self) -> EngineContext:
        shop = self.p.shop
        industry_code = (getattr(shop, "industry_code", None) or "default").strip().lower()
        rule_version = (getattr(shop, "rule_version", None) or "v1").strip()

        return EngineContext(
            tenant_id=getattr(self.p, "tenant_id", None),
            shop_id=getattr(self.p, "shop_id", None),
            industry_code=industry_code,
            rule_version=rule_version,
            request_id="",
        )

    def _ensure_months_active(self) -> int:
        """
        Nếu caller chưa truyền months_active thì tự tính an toàn:
        - exclude self.pk để tránh count sai khi update
        - nếu create (chưa pk) thì +1
        """
        if self.months_active > 0:
            return self.months_active

        qs = MonthlyPerformance.objects.filter(shop_id=self.p.shop_id)
        if self.p.pk:
            qs = qs.exclude(pk=self.p.pk)
        base = qs.count()
        return base if self.p.pk else (base + 1)

    def calculate(self) -> MonthlyPerformance:
        # -------------------------
        # Ensure required NOT NULL basics
        # -------------------------
        if getattr(self.p, "created_at", None) is None:
            self.p.created_at = timezone.now()

        # tenant_id should exist; model.save() usually sync from shop
        if not getattr(self.p, "tenant_id", None) and getattr(self.p, "shop_id", None):
            try:
                self.p.tenant_id = self.p.shop.tenant_id
            except Exception:
                pass

        # Normalize inputs (never None)
        self.p.revenue = d(getattr(self.p, "revenue", 0))
        self.p.cost = d(getattr(self.p, "cost", 0))
        self.p.fixed_fee = d(getattr(self.p, "fixed_fee", 0))
        self.p.vat_percent = d(getattr(self.p, "vat_percent", 0))
        self.p.sale_percent = d(getattr(self.p, "sale_percent", 0))
        self.p.growth_percent = d(getattr(self.p, "growth_percent", 0))

        months_active = self._ensure_months_active()

        # -------------------------
        # Call rule engine (founder controlled)
        # -------------------------
        ctx = self._ctx()
        as_of = self.p.month if isinstance(self.p.month, date) else timezone.now().date()
        engine = get_engine(ctx, as_of=as_of)

        out = engine.commission_calculate(
            CommissionInput(
                revenue=self.p.revenue,
                growth_percent=self.p.growth_percent,
                months_active=months_active,
            )
        )

        # From engine:
        # - gmv_fee_percent (percent number: 4 / 3.5 / 3)
        # - gmv_fee_amount
        # - gmv_net_after_tax
        # - team_percent
        # - team_bonus

        service_percent = d(out.gmv_fee_percent)          # 4.00
        percent_fee_amount = d(out.gmv_fee_amount)        # gross fee
        gmv_fee_after_tax = d(out.gmv_net_after_tax)      # after tax (70%)

        bonus_percent = d(out.team_percent)
        bonus_amount = d(out.team_bonus)

        # -------------------------
        # Fixed fee & sale commission (from model inputs)
        # -------------------------
        fixed_fee = self.p.fixed_fee
        vat_percent = self.p.vat_percent
        sale_percent = self.p.sale_percent

        fixed_fee_net = fixed_fee * (Decimal("1") - (vat_percent / Decimal("100")))
        fixed_fee_net_after_tax = fixed_fee_net * Decimal("0.70")
        sale_commission = fixed_fee_net_after_tax * (sale_percent / Decimal("100"))

        # -------------------------
        # Company net profit (DB field)
        # -------------------------
        company_net = (
            gmv_fee_after_tax
            + fixed_fee_net_after_tax
            - bonus_amount
            - sale_commission
        )

        snap = CommissionSnapshot(
            service_percent=q2(service_percent),
            percent_fee_amount=q2(percent_fee_amount),
            gmv_fee_after_tax=q2(gmv_fee_after_tax),
            bonus_percent=q2(bonus_percent),
            bonus_amount=q2(bonus_amount),
            fixed_fee_net=q2(fixed_fee_net),
            fixed_fee_net_after_tax=q2(fixed_fee_net_after_tax),
            sale_commission=q2(sale_commission),
            company_net_profit=q2(company_net),
        )

        # -------------------------
        # Write back to model (ALL NOT NULL)
        # -------------------------
        self.p.service_percent = snap.service_percent
        self.p.percent_fee_amount = snap.percent_fee_amount
        self.p.gmv_fee_after_tax = snap.gmv_fee_after_tax

        # profit base chart = gmv_fee_after_tax (như bạn đang dùng)
        self.p.profit = snap.gmv_fee_after_tax

        self.p.bonus_percent = snap.bonus_percent
        self.p.bonus_amount = snap.bonus_amount

        self.p.fixed_fee_net = snap.fixed_fee_net
        self.p.fixed_fee_net_after_tax = snap.fixed_fee_net_after_tax

        self.p.sale_commission = snap.sale_commission
        self.p.company_net_profit = snap.company_net_profit

        # Defensive: ensure absolutely no NOT NULL numeric becomes None
        for f in (
            "revenue",
            "cost",
            "service_percent",
            "percent_fee_amount",
            "profit",
            "growth_percent",
            "bonus_percent",
            "bonus_amount",
            "fixed_fee",
            "fixed_fee_net",
            "fixed_fee_net_after_tax",
            "gmv_fee_after_tax",
            "sale_commission",
            "vat_percent",
            "sale_percent",
            "company_net_profit",
        ):
            if getattr(self.p, f, None) is None:
                setattr(self.p, f, Decimal("0.00"))

        return self.p


# =====================================================
# AGENCY FINANCE CALCULATOR (optional keep)
# =====================================================
class AgencyFinanceCalculator:
    """
    Aggregate MonthlyPerformance into AgencyMonthlyFinance.
    """

    def __init__(self, month):
        self.month = month

    def calculate(self):
        from apps.finance.models import AgencyMonthlyFinance

        performances = MonthlyPerformance.objects.filter(month=self.month)

        total_gmv_fee = performances.aggregate(total=Sum("gmv_fee_after_tax"))["total"] or Decimal("0")
        total_fixed_fee = performances.aggregate(total=Sum("fixed_fee_net_after_tax"))["total"] or Decimal("0")
        total_sale = performances.aggregate(total=Sum("sale_commission"))["total"] or Decimal("0")
        total_team = performances.aggregate(total=Sum("bonus_amount"))["total"] or Decimal("0")

        operating_cost = Decimal("0")

        net = (
            d(total_gmv_fee)
            + d(total_fixed_fee)
            - d(total_sale)
            - d(total_team)
            - d(operating_cost)
        )

        AgencyMonthlyFinance.objects.update_or_create(
            month=self.month,
            defaults={
                "total_gmv_fee_after_tax": q2(d(total_gmv_fee)),
                "total_fixed_fee_net": q2(d(total_fixed_fee)),
                "total_sale_commission": q2(d(total_sale)),
                "total_team_bonus": q2(d(total_team)),
                "total_operating_cost": q2(d(operating_cost)),
                "agency_net_profit": q2(d(net)),
            },
        )