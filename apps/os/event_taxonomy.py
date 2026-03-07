from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


# ===== Namespace chuẩn =====
# work.*
# os.*
# notif.*
# system.*
#
# Quy ước:
# - name: lower snake with dots
# - payload: luôn có entity_kind/entity_id nếu liên quan entity
# - severity: info|warning|critical (optional)
#
# Mục tiêu: timeline + notifications + audit nhìn 1 format


WORK_ITEM_CREATED = "work.item.created"
WORK_ITEM_UPDATED = "work.item.updated"
WORK_ITEM_TRANSITIONED = "work.item.transitioned"
WORK_ITEM_COMMENTED = "work.item.commented"

OS_DECISION_CREATED = "os.decision.created"
OS_STRATEGY_CREATED = "os.strategy.created"
OS_ACTION_EXECUTED = "os.action.executed"

NOTIF_CREATED = "notif.created"


@dataclass(frozen=True)
class EventMeta:
    name: str
    tieu_de: str
    default_severity: str = "info"


REGISTRY: Dict[str, EventMeta] = {
    WORK_ITEM_CREATED: EventMeta(WORK_ITEM_CREATED, "Tạo công việc", "info"),
    WORK_ITEM_UPDATED: EventMeta(WORK_ITEM_UPDATED, "Cập nhật công việc", "info"),
    WORK_ITEM_TRANSITIONED: EventMeta(WORK_ITEM_TRANSITIONED, "Chuyển trạng thái", "info"),
    WORK_ITEM_COMMENTED: EventMeta(WORK_ITEM_COMMENTED, "Bình luận công việc", "info"),
    OS_DECISION_CREATED: EventMeta(OS_DECISION_CREATED, "OS sinh quyết định", "info"),
    OS_STRATEGY_CREATED: EventMeta(OS_STRATEGY_CREATED, "OS sinh chiến lược", "info"),
    OS_ACTION_EXECUTED: EventMeta(OS_ACTION_EXECUTED, "OS thực thi hành động", "info"),
    NOTIF_CREATED: EventMeta(NOTIF_CREATED, "Tạo thông báo", "info"),
}


def get_event_meta(name: str) -> EventMeta:
    n = (name or "").strip()
    return REGISTRY.get(n, EventMeta(n, f"Sự kiện: {n}", "info"))