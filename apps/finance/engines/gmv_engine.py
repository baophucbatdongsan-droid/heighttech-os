from decimal import Decimal


class GMVEngine:

    def __init__(self, performance, contract):
        self.performance = performance
        self.contract = contract

    def calculate(self):
        revenue = self.performance.revenue

        # Tiered rate
        if revenue < Decimal("1000000000"):
            rate = Decimal("4")
        elif revenue < Decimal("2000000000"):
            rate = Decimal("3.5")
        else:
            rate = Decimal("3")

        gmv_fee = revenue * rate / Decimal("100")

        return {
            "gmv_rate": rate,
            "gmv_fee": gmv_fee
        }