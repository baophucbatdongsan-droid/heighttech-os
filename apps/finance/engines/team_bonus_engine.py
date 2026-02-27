from decimal import Decimal


class TeamBonusEngine:

    def __init__(self, data, performance):
        self.data = data
        self.performance = performance

    def calculate(self):
        base = self.data["gmv_net_after_tax"]

        percent = Decimal("20")

        if self.performance.growth_percent >= 25:
            percent += Decimal("10")
        elif self.performance.growth_percent >= 15:
            percent += Decimal("5")

        if self.performance.month_count >= 6:
            percent += Decimal("2")

        team_bonus = base * percent / Decimal("100")

        return {
            "team_percent": percent,
            "team_bonus": team_bonus
        }