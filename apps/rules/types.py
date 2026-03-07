from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional

@dataclass(frozen=True)
class EngineContext:
    tenant_id: Optional[int]
    shop_id: Optional[int]
    industry_code: str
    rule_version: str
    request_id: str = ""

@dataclass(frozen=True)
class CommissionInput:
    revenue: Decimal
    growth_percent: Decimal
    months_active: int

@dataclass(frozen=True)
class CommissionOutput:
    gmv_fee_percent: Decimal
    gmv_fee_amount: Decimal
    gmv_net_after_tax: Decimal
    team_percent: Decimal
    team_bonus: Decimal
    fixed_fee: Decimal
    vat_rate: Decimal
    sale_percent: Decimal
    sale_bonus: Decimal
    agency_profit: Decimal

    def as_dict(self) -> Dict[str, Any]:
        # JSONField cần serialize, Decimal -> str để chắc ăn
        return {k: str(v) for k, v in self.__dict__.items()}