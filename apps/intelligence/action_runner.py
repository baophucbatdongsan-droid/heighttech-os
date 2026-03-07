from __future__ import annotations

from typing import List, Dict, Any

from .action_engine import execute_action


def run_actions(*, tenant_id: int, actions: List[Dict[str, Any]]):

    results = []

    for action in actions:
        result = execute_action(
            tenant_id=tenant_id,
            action=action,
        )
        results.append(result)

    return results