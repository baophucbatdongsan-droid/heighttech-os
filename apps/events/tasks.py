from __future__ import annotations

import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.events.bus import get_handlers
from apps.events.models import OutboxEvent

logger = logging.getLogger(__name__)


@shared_task(name="apps.events.tasks.process_outbox_events")
def process_outbox_events(batch_size: int = 100) -> dict:
    """
    Worker xử lý OutboxEvent:
    - lấy event status=new, available_at <= now
    - chuyển sang processing
    - gọi handlers đã register theo event.name
    - thành công -> done
    - lỗi -> failed
    """

    now = timezone.now()

    qs = (
        OutboxEvent.objects_all
        .filter(
            status=OutboxEvent.Status.NEW,
            available_at__lte=now,
        )
        .order_by("id")[:batch_size]
    )

    done_count = 0
    failed_count = 0
    skipped_count = 0

    for ev in qs:
        try:
            with transaction.atomic():
                locked = (
                    OutboxEvent.objects_all
                    .select_for_update()
                    .filter(id=ev.id)
                    .first()
                )
                if not locked:
                    skipped_count += 1
                    continue

                if locked.status != OutboxEvent.Status.NEW:
                    skipped_count += 1
                    continue

                locked.status = OutboxEvent.Status.PROCESSING
                locked.locked_at = now
                locked.attempts = int(locked.attempts or 0) + 1
                locked.save(update_fields=["status", "locked_at", "attempts", "updated_at"])

            handlers = get_handlers(locked.name)

            for handler in handlers:
                handler(locked)

            locked.status = OutboxEvent.Status.DONE
            locked.last_error = ""
            locked.save(update_fields=["status", "last_error", "updated_at"])
            done_count += 1

        except Exception as e:
            try:
                locked = OutboxEvent.objects_all.filter(id=ev.id).first()
                if locked:
                    locked.status = OutboxEvent.Status.FAILED
                    locked.last_error = str(e)[:5000]
                    locked.save(update_fields=["status", "last_error", "updated_at"])
            except Exception:
                pass

            failed_count += 1
            logger.exception("process_outbox_events failed: event_id=%s", getattr(ev, "id", None))

    return {
        "ok": True,
        "done": done_count,
        "failed": failed_count,
        "skipped": skipped_count,
    }