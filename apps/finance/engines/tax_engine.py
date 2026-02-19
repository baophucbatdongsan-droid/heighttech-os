from decimal import Decimal


class TaxEngine:

    def __init__(self, data):
        self.data = data

    def calculate(self):
        gmv_fee = self.data["gmv_fee"]

        # GMV chịu tổng 30%
        gmv_net = gmv_fee * Decimal("0.7")

        return {
            "gmv_net_after_tax": gmv_net
        }