# apps/events/event_registry.py
from __future__ import annotations

"""
HeightTech OS Event Taxonomy
Toàn bộ hệ thống chỉ emit event nằm trong registry này.
"""

EVENTS = {

    # =========================
    # OS CORE
    # =========================
    "os.system.started": {
        "entity": "system",
        "description": "OS system boot",
    },

    "os.decision.created": {
        "entity": "tenant",
        "description": "Decision engine tạo quyết định",
    },

    "os.strategy.created": {
        "entity": "tenant",
        "description": "OS sinh chiến lược",
    },

    "os.action.executed": {
        "entity": "action",
        "description": "OS thực thi action",
    },

    # =========================
    # WORK SYSTEM
    # =========================
    "work.item.created": {
        "entity": "workitem",
        "description": "Work item được tạo",
    },

    "work.item.updated": {
        "entity": "workitem",
        "description": "Work item được cập nhật",
    },

    "work.item.transitioned": {
        "entity": "workitem",
        "description": "Work item chuyển trạng thái",
    },

    # =========================
    # PROJECT
    # =========================
    "project.status.changed": {
        "entity": "project",
        "description": "Project đổi trạng thái",
    },

    # =========================
    # SHOP
    # =========================
    "shop.health.changed": {
        "entity": "shop",
        "description": "Health score của shop thay đổi",
    },

    # =========================
    # NOTIFICATIONS
    # =========================
    "notification.created": {
        "entity": "notification",
        "description": "Notification được tạo",
    },
}


def is_valid_event(name: str) -> bool:
    return name in EVENTS