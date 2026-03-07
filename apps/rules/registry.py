from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterable, List, Optional, Tuple, Type

from apps.rules.base import BaseRuleEngine


# ============================================================
# Types
# ============================================================

@dataclass(frozen=True)
class RuleRegistration:
    industry_code: str
    rule_version: str
    effective_date: date
    engine_cls: Type[BaseRuleEngine]


# ============================================================
# In-memory registry
# Key = (industry_code, rule_version, effective_date)
# ============================================================

_REGISTRY: Dict[Tuple[str, str, date], RuleRegistration] = {}


def _norm_industry_code(v: str) -> str:
    return (v or "").strip().lower()


def _norm_rule_version(v: str) -> str:
    # version string giữ nguyên semantics của bạn, chỉ trim
    return (v or "").strip()


def register(*, industry_code: str, rule_version: str, effective_date: date):
    """
    Decorator đăng ký engine theo:
    (industry_code, rule_version, effective_date)

    Quy ước:
    - industry_code: lowercase canonical
    - rule_version: string (vd "2026.02" hoặc "v1")
    - effective_date: date bắt đầu hiệu lực
    """

    if not isinstance(effective_date, date):
        raise TypeError("effective_date must be datetime.date")

    ind = _norm_industry_code(industry_code)
    ver = _norm_rule_version(rule_version)
    eff = effective_date

    if not ind:
        raise ValueError("industry_code is required")
    if not ver:
        raise ValueError("rule_version is required")

    def deco(engine_cls: Type[BaseRuleEngine]):
        key = (ind, ver, eff)
        if key in _REGISTRY:
            existed = _REGISTRY[key].engine_cls
            raise ValueError(
                "Duplicate rule registration for "
                f"(industry_code={ind}, rule_version={ver}, effective_date={eff}). "
                f"Already registered: {existed.__module__}.{existed.__name__}"
            )

        _REGISTRY[key] = RuleRegistration(
            industry_code=ind,
            rule_version=ver,
            effective_date=eff,
            engine_cls=engine_cls,
        )
        return engine_cls

    return deco


def list_rules(*, industry_code: Optional[str] = None, rule_version: Optional[str] = None) -> List[RuleRegistration]:
    """
    List registrations (sorted stable).
    Optional filter by industry_code and/or rule_version.
    """
    ind = _norm_industry_code(industry_code) if industry_code else None
    ver = _norm_rule_version(rule_version) if rule_version else None

    regs: Iterable[RuleRegistration] = _REGISTRY.values()
    if ind is not None:
        regs = [r for r in regs if r.industry_code == ind]
    if ver is not None:
        regs = [r for r in regs if r.rule_version == ver]

    return sorted(regs, key=lambda r: (r.industry_code, r.rule_version, r.effective_date))


# ============================================================
# Resolver
# ============================================================

def resolve_engine_cls(
    *,
    industry_code: str,
    rule_version: str,
    as_of: Optional[date] = None,
) -> Type[BaseRuleEngine]:
    """
    Resolve engine class theo:
    - (industry_code, rule_version)
    - chọn registration có effective_date <= as_of gần nhất
    - nếu as_of None -> dùng date.today()

    Raises:
        LookupError nếu không tìm được engine phù hợp
    """
    ind = _norm_industry_code(industry_code)
    ver = _norm_rule_version(rule_version)
    if not ind:
        raise ValueError("industry_code is required")
    if not ver:
        raise ValueError("rule_version is required")

    as_of_date = as_of or date.today()

    # Lọc candidates theo industry+version
    regs = [r for r in _REGISTRY.values() if r.industry_code == ind and r.rule_version == ver]
    if not regs:
        raise LookupError(f"No rules registered for industry_code={ind}, rule_version={ver}")

    # chỉ lấy những cái đã effective
    eligible = [r for r in regs if r.effective_date <= as_of_date]
    if not eligible:
        # có regs nhưng chưa cái nào tới effective date
        earliest = min(regs, key=lambda r: r.effective_date)
        raise LookupError(
            "No eligible rule for "
            f"industry_code={ind}, rule_version={ver}, as_of={as_of_date}. "
            f"Earliest effective_date is {earliest.effective_date}."
        )

    chosen = max(eligible, key=lambda r: r.effective_date)
    return chosen.engine_cls


def resolve_engine(
    *,
    industry_code: str,
    rule_version: str,
    as_of: Optional[date] = None,
    **engine_kwargs,
) -> BaseRuleEngine:
    """
    Resolve và instantiate engine.
    engine_kwargs forward cho engine ctor (nếu engine cần context).
    """
    cls = resolve_engine_cls(industry_code=industry_code, rule_version=rule_version, as_of=as_of)
    return cls(**engine_kwargs)


# ============================================================
# BACKWARD COMPAT SHIM
# ============================================================

class RuleRegistry:
    """
    Shim tương thích cho code cũ (vd apps/projects/services.py).

    - RuleRegistry.register(): deprecated -> raise rõ ràng
    - RuleRegistry.resolve(): forward sang resolve_engine_cls (hoặc resolve_engine tuỳ bạn)
    """

    @staticmethod
    def register(*args, **kwargs):
        raise NotImplementedError(
            "RuleRegistry.register is deprecated. "
            "Use @register(industry_code=..., rule_version=..., effective_date=...) "
            "decorator in apps.rules.registry."
        )

    @staticmethod
    def resolve(industry_code: str, rule_version: str, as_of: Optional[date] = None):
        # Trả engine class cho code cũ (thường code cũ expect class)
        return resolve_engine_cls(industry_code=industry_code, rule_version=rule_version, as_of=as_of)