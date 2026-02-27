from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Type

from apps.rules.base import BaseRuleEngine


@dataclass(frozen=True)
class RuleRegistration:
    industry_code: str
    rule_version: str
    effective_date: date
    engine_cls: Type[BaseRuleEngine]


_REGISTRY: List[RuleRegistration] = []


def register(*, industry_code: str, rule_version: str, effective_date: date):
    """
    Decorator đăng ký engine theo:
    (industry_code, rule_version, effective_date)
    """

    def deco(engine_cls: Type[BaseRuleEngine]):
        _REGISTRY.append(
            RuleRegistration(
                industry_code=industry_code,
                rule_version=rule_version,
                effective_date=effective_date,
                engine_cls=engine_cls,
            )
        )
        # sort stable
        _REGISTRY.sort(key=lambda r: (r.industry_code, r.rule_version, r.effective_date))
        return engine_cls

    return deco


def list_rules() -> List[RuleRegistration]:
    return list(_REGISTRY)

# ============================================================
# BACKWARD COMPAT SHIM (để code cũ không chết)
# - Một số chỗ (apps/projects/services.py ...) đang import RuleRegistry
# - Ở kiến trúc mới ta dùng engine registry + resolver, nhưng giữ shim
# ============================================================

class RuleRegistry:
    """
    Shim tương thích tạm thời.
    Không dùng cho logic mới.
    """
    @staticmethod
    def register(*args, **kwargs):
        raise NotImplementedError(
            "RuleRegistry.register is deprecated. Use @register(...) decorator in apps.rules.registry."
        )

    @staticmethod
    def resolve(*args, **kwargs):
        raise NotImplementedError(
            "RuleRegistry.resolve is deprecated. Use apps.rules.resolver.get_engine(...)."
        )