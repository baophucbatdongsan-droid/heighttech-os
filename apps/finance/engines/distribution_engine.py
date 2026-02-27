from decimal import Decimal


class DistributionEngine:

    def __init__(self, data):
        self.data = data

    def calculate(self):
        gmv_net = self.data["gmv_net_after_tax"]
        team_bonus = self.data["team_bonus"]
        sale_commission = self.data["sale_commission"]

        company_profit = gmv_net - team_bonus - sale_commission

        return {
            "company_profit": company_profit
        }