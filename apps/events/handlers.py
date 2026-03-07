# apps/events/handlers.py
from __future__ import annotations

from apps.events.bus import register_handler
from apps.events.models import EventOutbox


# =========================
# Example subscribers
# =========================
def on_work_item_created(evt: EventOutbox) -> None:
    """
    Khi work item created -> đẩy sang Action Engine / cập nhật metrics / ...
    Beta: làm nhẹ, chỉ log hoặc tạo action nếu cần.
    """
    # TODO: hook to apps.actions/services.py (sau)
    return


def on_work_item_updated(evt: EventOutbox) -> None:
    return


def bootstrap_handlers() -> None:
    register_handler("work.item.created", on_work_item_created)
    register_handler("work.item.updated", on_work_item_updated)