from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.core.exceptions import ValidationError

from .workflow_registry import registry


@dataclass(frozen=True)
class TransitionDecision:
    ok: bool
    reason: Optional[str] = None


class WorkflowEngine:
    """
    Engine thuần domain:
    - Không phụ thuộc DRF
    - Không mutate model
    - Chỉ validate và trả decision
    """

    def __init__(self, workflow_name: str = "workitem") -> None:
        self.workflow_name = workflow_name

    def decide(self, *, version: int, from_state: str, to_state: str) -> TransitionDecision:
        from_state = (from_state or "").strip().lower()
        to_state = (to_state or "").strip().lower()

        spec = registry.require(self.workflow_name, int(version))

        if from_state not in spec.states:
            return TransitionDecision(False, f"invalid_from_state: {from_state}")

        if to_state not in spec.states:
            return TransitionDecision(False, f"invalid_to_state: {to_state}")

        if not spec.allows(from_state, to_state):
            return TransitionDecision(False, f"transition_not_allowed: {from_state}->{to_state}")

        return TransitionDecision(True, None)

    def ensure(self, *, version: int, from_state: str, to_state: str) -> None:
        d = self.decide(version=version, from_state=from_state, to_state=to_state)
        if not d.ok:
            raise ValidationError(d.reason or "transition_not_allowed")