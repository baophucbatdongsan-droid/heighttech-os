# apps/intelligence/action_engine/__init__.py
from __future__ import annotations

from typing import Any, Dict


def execute_action(*, tenant_id: int, action: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute 1 action từ decision_engine.
    V1: noop an toàn để hệ thống chạy ổn trước.
    """
    action_type = (action.get("type") or "").strip().lower()

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "type": action_type or "unknown",
        "action": action,
        "result": "noop",
    }


def on_work_item_updated(event: Dict[str, Any]) -> None:
    """
    Handler khi WorkItem updated (event bus).
    V1: noop.
    """
    _ = event
    return

from apps.work.models import WorkItem


def execute_action(*, tenant_id: int, action: Dict[str, Any]) -> Dict[str, Any]:

    action_type = action.get("type")

    if action_type == "task.create":
        payload = action.get("payload", {})

        dedupe_key = payload.get("dedupe_key")

        if dedupe_key:
            exists = WorkItem.objects.filter(
                tenant_id=tenant_id,
                title=payload.get("title"),
                status="todo",
            ).exists()

            if exists:
                return {"status": "skipped_duplicate"}

        WorkItem.objects.create(
            tenant_id=tenant_id,
            title=payload.get("title", "Auto Task"),
            priority=payload.get("priority", 2),
            target_type=payload.get("target_type", ""),
            target_id=payload.get("target_id"),
        )

        return {"status": "task_created"}

    return {"status": "ignored"}