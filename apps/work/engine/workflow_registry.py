# apps/work/engine/workflow_registry.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from .workflow_v1 import WorkflowSpec, build_workflow_v1


@dataclass(frozen=True)
class WorkflowKey:
    name: str
    version: int


class WorkflowRegistry:
    """
    Registry giữ "workflow specs" theo (name, version).
    Quy tắc HeightTech:
    - Workflow/spec nằm trong code (versioned)
    - DB chỉ lưu rule_version / workflow_version (số)
    """
    def __init__(self) -> None:
        self._items: Dict[WorkflowKey, WorkflowSpec] = {}

    def register(self, spec: WorkflowSpec) -> None:
        key = WorkflowKey(spec.name, spec.version)
        self._items[key] = spec

    def get(self, name: str, version: int) -> Optional[WorkflowSpec]:
        return self._items.get(WorkflowKey(name, version))

    def require(self, name: str, version: int) -> WorkflowSpec:
        spec = self.get(name, version)
        if spec is None:
            raise KeyError(f"WorkflowSpec not found: {name}@v{version}")
        return spec


# Global singleton registry (đơn giản, deterministic)
registry = WorkflowRegistry()
registry.register(build_workflow_v1())