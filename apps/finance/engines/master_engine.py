from decimal import Decimal

from .gmv_engine import GMVEngine
from .tax_engine import TaxEngine
from .sale_engine import SaleEngine
from .team_bonus_engine import TeamBonusEngine
from .distribution_engine import DistributionEngine


class MasterEngine:

    def __init__(self, performance, contract):
        self.performance = performance
        self.contract = contract

    def run(self):
        result = {}

        # 1. GMV Commission
        gmv_data = GMVEngine(self.performance, self.contract).calculate()
        result.update(gmv_data)

        # 2. Tax
        tax_data = TaxEngine(result).calculate()
        result.update(tax_data)

        # 3. Sale Commission
        sale_data = SaleEngine(result, self.contract).calculate()
        result.update(sale_data)

        # 4. Team Bonus
        team_data = TeamBonusEngine(result, self.performance).calculate()
        result.update(team_data)

        # 5. Distribution
        distribution = DistributionEngine(result).calculate()
        result.update(distribution)

        return result