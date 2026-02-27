from __future__ import annotations

from datetime import date
from typing import Type

from apps.rules.base import BaseRuleEngine
from apps.rules.models import RuleRelease
from apps.rules.registry import list_rules
from apps.rules.types import EngineContext


def _best_enabled_version(industry_code: str, as_of: date) -> str | None:
    """
    Pick rule_version enabled mới nhất theo effective_from (<= as_of).
    """
    qs = (
        RuleRelease.objects
        .filter(industry_code=industry_code, is_enabled=True, effective_from__lte=as_of)
        .order_by("-effective_from", "-id")
        .values_list("rule_version", flat=True)
    )
    return qs.first()


def resolve_engine_cls(industry_code: str, rule_version: str, as_of: date) -> Type[BaseRuleEngine]:
    # 1) Nếu DB có release enabled thì ưu tiên version đó (founder control)
    picked = _best_enabled_version(industry_code, as_of)
    if picked:
        rule_version = picked

    # 2) Resolve theo code registry
    candidates = [
        r for r in list_rules()
        if r.industry_code == industry_code and r.rule_version == rule_version and r.effective_date <= as_of
    ]

    # fallback về default/v1
    if not candidates:
        picked_default = _best_enabled_version("default", as_of) or "v1"
        candidates = [
            r for r in list_rules()
            if r.industry_code == "default" and r.rule_version == picked_default and r.effective_date <= as_of
        ]

    if not candidates:
        raise RuntimeError("No rules registered. Ensure apps.rules.policies is imported at startup.")

    candidates.sort(key=lambda r: r.effective_date)
    return candidates[-1].engine_cls


def get_engine(ctx: EngineContext, as_of: date) -> BaseRuleEngine:
    cls = resolve_engine_cls(ctx.industry_code, ctx.rule_version, as_of)
    return cls(ctx)