# apps/intelligence/strategy_actions.py
from __future__ import annotations

from typing import Any, Dict, List

from apps.intelligence.strategy_engine import StrategyPlan


def plans_to_actions(plans: List[Dict[str, Any]] | List[StrategyPlan]) -> List[Dict[str, Any]]:
    """
    Convert plans -> list actions cho ActionRunner.
    Output format:
      [{"type": "...", "payload": {...}}, ...]
    """
    actions: List[Dict[str, Any]] = []

    # case 1: plans already dict (plans_to_dict output)
    if plans and isinstance(plans[0], dict):  # type: ignore[index]
        for p in plans:  # type: ignore[assignment]
            for a in (p or {}).get("actions", []) or []:
                t = (a or {}).get("type")
                payload = (a or {}).get("payload") or {}
                if t:
                    actions.append({"type": str(t), "payload": dict(payload)})
        return actions

    # case 2: dataclass StrategyPlan
    for p in plans or []:  # type: ignore[assignment]
        for a in getattr(p, "actions", []) or []:
            t = getattr(a, "type", None)
            payload = getattr(a, "payload", {}) or {}
            if t:
                actions.append({"type": str(t), "payload": dict(payload)})

    return actions