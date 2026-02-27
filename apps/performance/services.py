from decimal import Decimal
from django.db.models import Sum
from apps.performance.models import MonthlyPerformance
from apps.finance.models import AgencyMonthlyFinance

# ============================
# CONSTANTS
# ============================

TNDN_TOTAL = Decimal("0.30")        # tổng thuế 30% cho GMV fee
AFTER_TAX_RATE = Decimal("0.70")    # còn lại 70%

BONUS_BASE = Decimal("20")
BONUS_GROWTH_15 = Decimal("5")
BONUS_GROWTH_25 = Decimal("10")
BONUS_KEEP_6M = Decimal("2")

MAX_BONUS = Decimal("32")           # 20 + 10 + 2


# =====================================================
# PERFORMANCE CALCULATOR
# =====================================================

class PerformanceCalculator:
    """
    Calculator cho MonthlyPerformance
    Không import model ở top để tránh circular import
    """

    def __init__(self, perf):
        self.p = perf

    # ============================
    # HELPERS
    # ============================

    def _d(self, value):
        return Decimal(value or 0)

    def _q(self, value):
        return value.quantize(Decimal("0.01"))

    # ============================
    # SERVICE PERCENT TIERS
    # ============================

    def resolve_service_percent(self) -> Decimal:
        """
        Rule:
        - GMV < 1B: 4%
        - 1B - 2B: 3.5%
        - > 2B: 3%
        """

        rev = self._d(self.p.revenue)

        if self._d(self.p.service_percent) > 0:
            return self._d(self.p.service_percent)

        if rev < Decimal("1000000000"):
            return Decimal("4.00")

        if rev < Decimal("2000000000"):
            return Decimal("3.50")

        return Decimal("3.00")

    # ============================
    # GROWTH
    # ============================

    def resolve_growth_percent(self) -> Decimal:
        Model = self.p.__class__

        prev = (
            Model.objects
            .filter(shop=self.p.shop, month__lt=self.p.month)
            .order_by("-month")
            .first()
        )

        cur_rev = self._d(self.p.revenue)

        if prev and self._d(prev.revenue) > 0:
            prev_rev = self._d(prev.revenue)
            return ((cur_rev - prev_rev) / prev_rev) * Decimal("100")

        if (not prev) and cur_rev > 0:
            return Decimal("100")

        return Decimal("0")

    # ============================
    # BONUS RATE
    # ============================

    def resolve_bonus_percent(self, growth: Decimal) -> Decimal:

        bonus = BONUS_BASE

        if growth > Decimal("25"):
            bonus += BONUS_GROWTH_25
        elif growth > Decimal("15"):
            bonus += BONUS_GROWTH_15

        Model = self.p.__class__
        months_active = Model.objects.filter(shop=self.p.shop).count()

        if months_active >= 6:
            bonus += BONUS_KEEP_6M

        if bonus > MAX_BONUS:
            bonus = MAX_BONUS

        return bonus

    # ============================
    # MAIN CALCULATION
    # ============================

    def calculate(self):

        # Service percent
        self.p.service_percent = self.resolve_service_percent()

        revenue = self._d(self.p.revenue)
        service_percent = self._d(self.p.service_percent)

        percent_fee_amount = revenue * (service_percent / Decimal("100"))
        self.p.percent_fee_amount = self._q(percent_fee_amount)

        # GMV fee after tax
        gmv_fee_after_tax = percent_fee_amount * AFTER_TAX_RATE
        self.p.gmv_fee_after_tax = self._q(gmv_fee_after_tax)

        # Base profit
        self.p.profit = self._q(gmv_fee_after_tax)

        # Growth
        growth = self.resolve_growth_percent()
        self.p.growth_percent = self._q(growth)

        # Bonus
        bonus_percent = self.resolve_bonus_percent(growth)
        self.p.bonus_percent = self._q(bonus_percent)

        bonus_amount = self.p.profit * (bonus_percent / Decimal("100"))
        self.p.bonus_amount = self._q(bonus_amount)

        # Fixed fee VAT xử lý
        fixed_fee = self._d(self.p.fixed_fee)
        vat_percent = self._d(self.p.vat_percent)

        fixed_fee_net = fixed_fee * (Decimal("1") - (vat_percent / Decimal("100")))
        self.p.fixed_fee_net = self._q(fixed_fee_net)

        fixed_fee_net_after_tax = fixed_fee_net * AFTER_TAX_RATE
        self.p.fixed_fee_net_after_tax = self._q(fixed_fee_net_after_tax)

        # Sale commission
        sale_percent = self._d(self.p.sale_percent)
        sale_commission = fixed_fee_net_after_tax * (sale_percent / Decimal("100"))
        self.p.sale_commission = self._q(sale_commission)

        # Company net profit
        company_net = (
            self.p.gmv_fee_after_tax
            + self.p.fixed_fee_net_after_tax
            - self.p.bonus_amount
            - self.p.sale_commission
        )

        self.p.company_net_profit = self._q(company_net)


# =====================================================
# AGENCY FINANCE CALCULATOR
# =====================================================

class AgencyFinanceCalculator:

    def __init__(self, month):
        self.month = month

    def calculate(self):

        # import local tránh circular
        from .models import MonthlyPerformance, AgencyMonthlyFinance

        performances = MonthlyPerformance.objects.filter(
            month=self.month
        )

        total_gmv_fee = performances.aggregate(
            total=Sum("gmv_fee_after_tax")
        )["total"] or Decimal("0")

        total_fixed_fee = performances.aggregate(
            total=Sum("fixed_fee_net_after_tax")
        )["total"] or Decimal("0")

        total_sale = performances.aggregate(
            total=Sum("sale_commission")
        )["total"] or Decimal("0")

        total_team = performances.aggregate(
            total=Sum("bonus_amount")
        )["total"] or Decimal("0")

        operating_cost = Decimal("0")

        net = (
            total_gmv_fee
            + total_fixed_fee
            - total_sale
            - total_team
            - operating_cost
        )

        AgencyMonthlyFinance.objects.update_or_create(
            month=self.month,
            defaults={
                "total_gmv_fee_after_tax": total_gmv_fee,
                "total_fixed_fee_net": total_fixed_fee,
                "total_sale_commission": total_sale,
                "total_team_bonus": total_team,
                "total_operating_cost": operating_cost,
                "agency_net_profit": net,
            }
        )