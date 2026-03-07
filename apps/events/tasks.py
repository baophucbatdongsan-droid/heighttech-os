# apps/events/tasks.py
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.events.bus import dispatch_event
from apps.events.models import EventOutbox

try:
    from celery import shared_task
except Exception:  # pragma: no cover
    shared_task = None  # type: ignore


def _pump(limit: int = 200) -> int:
    """
    Atomically claim events to avoid 2 workers xử lý cùng event.
    Using SELECT FOR UPDATE SKIP LOCKED (Postgres).
    """
    now = timezone.now()
    processed = 0

    with transaction.atomic():
        qs = (
            EventOutbox.objects.select_for_update(skip_locked=True)
            .filter(status=EventOutbox.Status.PENDING)
            .order_by("id")[:limit]
        )
        events = list(qs)

        for evt in events:
            try:
                dispatch_event(evt)
                evt.status = EventOutbox.Status.PUBLISHED
                evt.published_at = now
                evt.last_error = ""
                evt.save(update_fields=["status", "published_at", "last_error", "updated_at"])
            except Exception as e:
                evt.fail_count = int(evt.fail_count or 0) + 1
                evt.status = EventOutbox.Status.FAILED if evt.fail_count >= 10 else EventOutbox.Status.PENDING
                evt.last_error = str(e)[:4000]
                evt.save(update_fields=["status", "fail_count", "last_error", "updated_at"])
            processed += 1

    return processed


if shared_task:
    @shared_task(name="events.pump_outbox")
    def pump_outbox_task(limit: int = 200) -> int:
        return _pump(limit=limit)