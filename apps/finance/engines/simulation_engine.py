from decimal import Decimal


class SimulationEngine:

    @staticmethod
    def simulate(revenue):
        if revenue < Decimal("1000000000"):
            rate = Decimal("4")
        elif revenue < Decimal("2000000000"):
            rate = Decimal("3.5")
        else:
            rate = Decimal("3")

        gmv_fee = revenue * rate / Decimal("100")
        gmv_net = gmv_fee * Decimal("0.7")

        return {
            "revenue": revenue,
            "gmv_fee": gmv_fee,
            "gmv_net_after_tax": gmv_net
        }