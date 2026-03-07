# apps/rules/policies/v1_default.py
from __future__ import annotations

from datetime import date
from decimal import Decimal

from apps.rules.base import BaseRuleEngine
from apps.rules.registry import register
from apps.rules.types import CommissionInput, CommissionOutput


@register(industry_code="ecommerce", rule_version="v1", effective_date=date(2020, 1, 1))
@register(industry_code="default", rule_version="v1", effective_date=date(2020, 1, 1))
class DefaultV1Engine(BaseRuleEngine):
    ENGINE_NAME = "default_v1"

    def commission_calculate(self, inp: CommissionInput) -> CommissionOutput:
        if inp.revenue < Decimal("1000000000"):
            gmv_percent = Decimal("4")
        elif inp.revenue < Decimal("2000000000"):
            gmv_percent = Decimal("3.5")
        else:
            gmv_percent = Decimal("3")

        gmv_fee = inp.revenue * gmv_percent / Decimal("100")
        gmv_net = gmv_fee * Decimal("0.7")

        team_percent = Decimal("20")
        if inp.growth_percent >= Decimal("25"):
            team_percent += Decimal("10")
        elif inp.growth_percent >= Decimal("15"):
            team_percent += Decimal("5")
        if inp.months_active >= 6:
            team_percent += Decimal("2")

        team_bonus = gmv_net * team_percent / Decimal("100")

        fixed_fee = Decimal("8000000")
        vat_rate = Decimal("0.10")
        fixed_net = fixed_fee * (Decimal("1") - vat_rate)

        sale_percent = Decimal("5")
        sale_bonus = fixed_net * sale_percent / Decimal("100")

        agency_profit = gmv_net - team_bonus - sale_bonus

        out = CommissionOutput(
            gmv_fee_percent=gmv_percent,
            gmv_fee_amount=gmv_fee,
            gmv_net_after_tax=gmv_net,
            team_percent=team_percent,
            team_bonus=team_bonus,
            fixed_fee=fixed_fee,
            vat_rate=vat_rate,
            sale_percent=sale_percent,
            sale_bonus=sale_bonus,
            agency_profit=agency_profit,
        )

        self.log_decision(
            rule_key="commission.calculate",
            input_snapshot={
                "revenue": str(inp.revenue),
                "growth_percent": str(inp.growth_percent),
                "months_active": inp.months_active,
            },
            output_result=out.as_dict(),
        )
        return out
    



@register(industry_code="default", rule_version="v1", effective_date=date(2026, 1, 1))
class DefaultV1Engine(BaseRuleEngine):
    ENGINE_NAME = "default_v1"

    def commission_calculate(self, inp: CommissionInput) -> CommissionOutput:
        if inp.revenue < Decimal("1000000000"):
            gmv_percent = Decimal("4")
        elif inp.revenue < Decimal("2000000000"):
            gmv_percent = Decimal("3.5")
        else:
            gmv_percent = Decimal("3")

        gmv_fee = inp.revenue * gmv_percent / Decimal("100")
        gmv_net = gmv_fee * Decimal("0.7")

        team_percent = Decimal("20")
        if inp.growth_percent > Decimal("25"):
            team_percent += Decimal("10")
        elif inp.growth_percent > Decimal("15"):
            team_percent += Decimal("5")
        if inp.months_active >= 6:
            team_percent += Decimal("2")

        team_bonus = gmv_net * team_percent / Decimal("100")

        fixed_fee = Decimal("8000000")
        vat_rate = Decimal("0.10")
        fixed_net = fixed_fee * (Decimal("1") - vat_rate)

        sale_percent = Decimal("5")
        sale_bonus = fixed_net * sale_percent / Decimal("100")

        agency_profit = gmv_net - team_bonus - sale_bonus

        out = CommissionOutput(
            gmv_fee_percent=gmv_percent,
            gmv_fee_amount=gmv_fee,
            gmv_net_after_tax=gmv_net,
            team_percent=team_percent,
            team_bonus=team_bonus,
            fixed_fee=fixed_fee,
            vat_rate=vat_rate,
            sale_percent=sale_percent,
            sale_bonus=sale_bonus,
            agency_profit=agency_profit,
        )

        self.log_decision(
            rule_key="commission.calculate",
            input_snapshot={
                "revenue": str(inp.revenue),
                "growth_percent": str(inp.growth_percent),
                "months_active": inp.months_active,
            },
            output_result=out.as_dict(),
        )
        return out


@register(industry_code="ecommerce", rule_version="v1", effective_date=date(2026, 1, 1))
class EcommerceV1Engine(DefaultV1Engine):
    ENGINE_NAME = "ecommerce_v1"