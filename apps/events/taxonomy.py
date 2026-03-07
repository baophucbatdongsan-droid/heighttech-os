# apps/events/taxonomy.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any


@dataclass(frozen=True)
class EventDef:
    name: str
    version: int
    tieu_de: str
    nhom: str  # work | os | shop | system
    mo_ta: str = ""


# ==== WORK ====
WORK_ITEM_CREATED = EventDef(
    name="work.item.created",
    version=1,
    tieu_de="Tạo công việc",
    nhom="work",
)
WORK_ITEM_UPDATED = EventDef(
    name="work.item.updated",
    version=1,
    tieu_de="Cập nhật công việc",
    nhom="work",
)
WORK_ITEM_TRANSITIONED = EventDef(
    name="work.item.transitioned",
    version=1,
    tieu_de="Chuyển trạng thái công việc",
    nhom="work",
)

# ==== OS ====
OS_DECISION_CREATED = EventDef(
    name="os.decision.created",
    version=1,
    tieu_de="Sinh quyết định",
    nhom="os",
)
OS_STRATEGY_CREATED = EventDef(
    name="os.strategy.created",
    version=1,
    tieu_de="Sinh chiến lược",
    nhom="os",
)
OS_ACTION_EXECUTED = EventDef(
    name="os.action.executed",
    version=1,
    tieu_de="Thực thi hành động",
    nhom="os",
)

# registry (để validate)
REGISTRY: Dict[str, EventDef] = {
    e.name: e
    for e in [
        WORK_ITEM_CREATED,
        WORK_ITEM_UPDATED,
        WORK_ITEM_TRANSITIONED,
        OS_DECISION_CREATED,
        OS_STRATEGY_CREATED,
        OS_ACTION_EXECUTED,
    ]
}


def require_event(name: str) -> EventDef:
    n = (name or "").strip()
    if n in REGISTRY:
        return REGISTRY[n]
    # fallback: vẫn cho chạy beta, nhưng đẩy vào “system”
    return EventDef(name=n, version=1, tieu_de=f"Sự kiện: {n}", nhom="system")