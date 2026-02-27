from decimal import Decimal


class SaleEngine:

    def __init__(self, data, contract):
        self.data = data
        self.contract = contract

    def calculate(self):
        fixed_fee = self.contract.fixed_fee
        vat_rate = self.contract.vat_percent

        # VAT loại khỏi phí cứng
        fixed_after_vat = fixed_fee / (1 + vat_rate / Decimal("100"))

        # Sau thuế TNDN 20%
        fixed_after_tax = fixed_after_vat * Decimal("0.8")

        sale_percent = self.contract.sale_percent

        sale_commission = fixed_after_tax * sale_percent / Decimal("100")

        return {
            "fixed_after_tax": fixed_after_tax,
            "sale_commission": sale_commission
        }