from __future__ import annotations

import logging

from apps.events.bus import register
from apps.notifications.handlers import on_outbox_event_to_notification

logger = logging.getLogger(__name__)


def setup_handlers() -> None:
    register("work.item.created", on_outbox_event_to_notification)
    register("work.item.updated", on_outbox_event_to_notification)
    register("work.item.transitioned", on_outbox_event_to_notification)

    # os.* nếu anh emit sau này
    register("os.decision.created", on_outbox_event_to_notification)
    register("os.strategy.created", on_outbox_event_to_notification)
    register("os.action.executed", on_outbox_event_to_notification)

    logger.info("Notifications handlers registered")