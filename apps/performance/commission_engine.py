from decimal import Decimal
from django.apps import apps


class CommissionEngine:

    def __init__(self, performance):
        self.performance = performance
        self.shop = performance.shop

    # =========================
    # GMV RATE
    # =========================
    def get_gmv_percent(self, gmv):
        if gmv < 1_000_000_000:
            return Decimal("4")
        elif gmv < 2_000_000_000:
            return Decimal("3.5")
        return Decimal("3")

    # =========================
    # TEAM %
    # =========================
    def get_team_percent(self, growth, months_active):
        percent = Decimal("20")

        if growth > 25:
            percent += Decimal("10")
        elif growth > 15:
            percent += Decimal("5")

        if months_active >= 6:
            percent += Decimal("2")

        return percent

    # =========================
    # MAIN CALC
    # =========================
    def calculate(self):

        CommissionLedger = apps.get_model("performance", "CommissionLedger")

        gmv = self.performance.revenue
        growth = self.performance.growth_percent

        gmv_percent = self.get_gmv_percent(gmv)
        gmv_fee = gmv * gmv_percent / 100

        gmv_net = gmv_fee * Decimal("0.7")

        months_active = self.shop.performances.count()
        team_percent = self.get_team_percent(growth, months_active)
        team_bonus = gmv_net * team_percent / 100

        fixed_fee = Decimal("8000000")
        vat_rate = Decimal("0.10")
        fixed_net = fixed_fee * (1 - vat_rate)

        sale_percent = Decimal("5")
        sale_bonus = fixed_net * sale_percent / 100

        agency_profit = gmv_net - team_bonus - sale_bonus

        ledger, _ = CommissionLedger.objects.update_or_create(
            shop=self.shop,
            month=self.performance.month,
            defaults={
                "gmv": gmv,
                "gmv_fee_percent": gmv_percent,
                "gmv_fee_amount": gmv_fee,
                "gmv_net_after_tax": gmv_net,
                "team_percent": team_percent,
                "team_bonus": team_bonus,
                "fixed_fee": fixed_fee,
                "vat_rate": vat_rate,
                "sale_percent": sale_percent,
                "sale_bonus": sale_bonus,
                "agency_profit": agency_profit,
            }
        )

        return ledger