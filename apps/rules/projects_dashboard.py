from __future__ import annotations

from datetime import date
from typing import Tuple

from .registry import RuleRegistry, RuleSpec

DOMAIN = "projects_dashboard"


def _rule_v1(*, total: int, done: int, paused: int, inactive: int) -> Tuple[int, int]:
    # GIỮ Y NGUYÊN logic cũ để không phá
    progress = int(round((done / total) * 100)) if total else 0

    health = 100
    health -= paused * 10
    health -= inactive * 15
    health -= max(0, total - done) * 1
    health = max(0, min(100, health))
    return progress, health


def register_projects_dashboard_rules() -> None:
    # default cho mọi type_code
    RuleRegistry.register(
        domain=DOMAIN,
        key="default",
        rule=RuleSpec(version="v1", effective_from=date(2026, 1, 1), fn=_rule_v1),
    )

    # Nếu sau này muốn tách theo ngành/type_code:
    # RuleRegistry.register(domain=DOMAIN, key="ecom", rule=RuleSpec(version="v2", effective_from=date(2026, 3, 1), fn=_rule_v2))