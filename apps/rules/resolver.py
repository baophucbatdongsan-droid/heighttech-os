# apps/rules/resolver.py
from __future__ import annotations

from datetime import date
from typing import Type, Optional

from apps.rules.base import BaseRuleEngine
from apps.rules.models import RuleRelease
from apps.rules.types import EngineContext

from apps.rules.registry import resolve_engine_cls as registry_resolve_engine_cls
from apps.rules.registry import list_rules


def _norm_industry_code(v: str) -> str:
    return (v or "").strip().lower()


def _norm_rule_version(v: str) -> str:
    return (v or "").strip()


def _best_enabled_version(industry_code: str, as_of: date) -> str | None:
    ind = _norm_industry_code(industry_code)
    qs = (
        RuleRelease.objects
        .filter(industry_code=ind, is_enabled=True, effective_from__lte=as_of)
        .order_by("-effective_from", "-id")
        .values_list("rule_version", flat=True)
    )
    return qs.first()


def _earliest_effective_date(industry_code: str, rule_version: str) -> Optional[date]:
    regs = list_rules(industry_code=_norm_industry_code(industry_code), rule_version=_norm_rule_version(rule_version))
    if not regs:
        return None
    regs.sort(key=lambda r: r.effective_date)
    return regs[0].effective_date


def _resolve_with_earliest_fallback(industry_code: str, rule_version: str, as_of: date) -> Type[BaseRuleEngine]:
    ind = _norm_industry_code(industry_code)
    ver = _norm_rule_version(rule_version)

    try:
        return registry_resolve_engine_cls(industry_code=ind, rule_version=ver, as_of=as_of)
    except LookupError:
        earliest = _earliest_effective_date(ind, ver)
        if earliest:
            return registry_resolve_engine_cls(industry_code=ind, rule_version=ver, as_of=earliest)
        raise


def resolve_engine_cls(industry_code: str, rule_version: str, as_of: date) -> Type[BaseRuleEngine]:
    ind = _norm_industry_code(industry_code)
    ver = _norm_rule_version(rule_version)

    picked = _best_enabled_version(ind, as_of)
    if picked:
        ver = _norm_rule_version(picked)

    # 1) resolve normal (+ kẹp earliest nếu as_of quá sớm)
    try:
        return _resolve_with_earliest_fallback(industry_code=ind, rule_version=ver, as_of=as_of)
    except LookupError:
        pass

    # 2) fallback default (+ kẹp earliest)
    default_ver = _best_enabled_version("default", as_of) or "v1"
    return _resolve_with_earliest_fallback(industry_code="default", rule_version=default_ver, as_of=as_of)


def get_engine(ctx: EngineContext, as_of: date) -> BaseRuleEngine:
    cls = resolve_engine_cls(ctx.industry_code, ctx.rule_version, as_of)
    return cls(ctx)