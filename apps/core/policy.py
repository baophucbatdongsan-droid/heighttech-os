# apps/core/policy.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet

# ===== abilities (permission names) =====
VIEW_DASHBOARD = "view_dashboard"
VIEW_FOUNDER = "view_founder"

VIEW_API_DASHBOARD = "api:view_dashboard"
VIEW_API_FOUNDER = "api:view_founder"

IMPORT_MONTHLY_PERFORMANCE = "api:import_monthly_performance"

# ===== role names =====
ROLE_FOUNDER = "founder"
ROLE_HEAD = "head"
ROLE_ACCOUNT = "account"
ROLE_SALE = "sale"
ROLE_OPERATOR = "operator"
ROLE_CLIENT = "client"
ROLE_NONE = "none"

# ✅ thêm role leader/editor
ROLE_LEADER_OPERATION = "leader_operation"
ROLE_LEADER_CHANNEL = "leader_channel"
ROLE_LEADER_BOOKING = "leader_booking"
ROLE_EDITOR = "editor"


@dataclass(frozen=True)
class Policy:
    role_to_abilities: Dict[str, FrozenSet[str]]


DEFAULT_POLICY = Policy(
    role_to_abilities={

        ROLE_FOUNDER: frozenset({
            VIEW_DASHBOARD,
            VIEW_FOUNDER,
            VIEW_API_DASHBOARD,
            VIEW_API_FOUNDER,
            IMPORT_MONTHLY_PERFORMANCE,
        }),

        ROLE_HEAD: frozenset({
            VIEW_DASHBOARD,
            VIEW_API_DASHBOARD,
            IMPORT_MONTHLY_PERFORMANCE,
        }),

        ROLE_ACCOUNT: frozenset({
            VIEW_DASHBOARD,
            VIEW_API_DASHBOARD,
            IMPORT_MONTHLY_PERFORMANCE,
        }),

        ROLE_SALE: frozenset({
            VIEW_DASHBOARD,
            VIEW_API_DASHBOARD,
        }),

        ROLE_OPERATOR: frozenset({
            VIEW_DASHBOARD,
            VIEW_API_DASHBOARD,
        }),

        ROLE_CLIENT: frozenset({
            VIEW_DASHBOARD,
            VIEW_API_DASHBOARD,
        }),

        # ✅ leader roles
        ROLE_LEADER_OPERATION: frozenset({
            VIEW_DASHBOARD,
            VIEW_API_DASHBOARD,
        }),

        ROLE_LEADER_CHANNEL: frozenset({
            VIEW_DASHBOARD,
            VIEW_API_DASHBOARD,
        }),

        ROLE_LEADER_BOOKING: frozenset({
            VIEW_DASHBOARD,
            VIEW_API_DASHBOARD,
        }),

        ROLE_EDITOR: frozenset({
            VIEW_DASHBOARD,
            VIEW_API_DASHBOARD,
        }),

        ROLE_NONE: frozenset(),
    }
)


def role_has_ability(role: str, ability: str) -> bool:
    role = (role or ROLE_NONE).lower()
    return ability in DEFAULT_POLICY.role_to_abilities.get(role, frozenset())