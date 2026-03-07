# apps/core/events.py
from dataclasses import dataclass
from typing import Any, Dict, Optional
from datetime import datetime


@dataclass
class DomainEvent:
    name: str
    model: str
    object_id: str
    tenant_id: int
    actor_id: Optional[int] = None
    payload: Optional[Dict[str, Any]] = None
    created_at: datetime = datetime.utcnow()

    _event_handlers = []


def register_event_handler(handler):
    _event_handlers.append(handler)


def dispatch_event(event: DomainEvent):
    for handler in _event_handlers:
        try:
            handler(event)
        except Exception:
            # Event không được crash flow
            continue