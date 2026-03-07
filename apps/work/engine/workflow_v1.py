# apps/work/engine/workflow_v1.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet


@dataclass(frozen=True)
class WorkflowSpec:
    name: str
    version: int
    states: FrozenSet[str]
    transitions: Dict[str, FrozenSet[str]]

    def allows(self, from_state: str, to_state: str) -> bool:
        tos = self.transitions.get(from_state)
        return bool(tos and to_state in tos)


def build_workflow_v1() -> WorkflowSpec:
    # ✅ match UI: todo/doing/blocked/done/cancelled
    states = frozenset({"todo", "doing", "blocked", "done", "cancelled"})
    transitions: Dict[str, FrozenSet[str]] = {
        "todo": frozenset({"doing", "blocked", "cancelled"}),
        "doing": frozenset({"todo", "blocked", "done", "cancelled"}),
        "blocked": frozenset({"todo", "doing", "cancelled"}),
        "done": frozenset({"todo"}),          # optional: allow reopen
        "cancelled": frozenset({"todo"}),     # optional: revive
    }
    return WorkflowSpec(
        name="workitem",
        version=1,
        states=states,
        transitions=transitions,
    )