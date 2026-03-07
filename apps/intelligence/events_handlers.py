# apps/intelligence/events_handlers.py
from __future__ import annotations

import logging
from apps.events.bus import register

logger = logging.getLogger(__name__)

# Guard để tránh register trùng
_HANDLERS_READY = False


def setup_handlers() -> None:
    """
    FINAL:
    - Idempotent: gọi nhiều lần cũng chỉ register 1 lần.
    - Safe import: không crash hệ thống nếu handler thiếu/hỏng.
    """
    global _HANDLERS_READY
    if _HANDLERS_READY:
        return

    try:
        # ✅ Chuẩn tên module: action_engine.py
        from apps.intelligence.action_engine import on_work_item_updated
    except Exception:
        logger.exception("Cannot import on_work_item_updated from apps.intelligence.action_engine")
        return

    # Register events (WorkItem create/update)
    register("work.item.created", on_work_item_updated)
    register("work.item.updated", on_work_item_updated)

    _HANDLERS_READY = True
    logger.info("Intelligence event handlers registered")