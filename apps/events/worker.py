# apps/events/worker.py
from __future__ import annotations

import logging
import time
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.events.bus import get_handlers
from apps.events.models import OutboxEvent
from django.db import models
logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 12
DEFAULT_LEASE_TTL_SECONDS = 300  # 5 phút: event PROCESSING kẹt quá lâu -> lấy lại


def _lease_one(
    *,
    now=None,
    lease_ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
) -> Optional[OutboxEvent]:
    now = now or timezone.now()
    ttl_cutoff = now - timezone.timedelta(seconds=max(30, int(lease_ttl_seconds or 300)))

    with transaction.atomic():
        qs = (
            OutboxEvent.objects_all.select_for_update(skip_locked=True)
            .filter(available_at__lte=now)
            .filter(
                # NEW hoặc PROCESSING bị kẹt (worker chết giữa chừng)
                models.Q(status=OutboxEvent.Status.NEW)
                | models.Q(status=OutboxEvent.Status.PROCESSING, locked_at__lt=ttl_cutoff)
            )
            .order_by("id")
        )

        ev = qs.first()
        if not ev:
            return None

        ev.status = OutboxEvent.Status.PROCESSING
        ev.locked_at = now
        ev.attempts = int(ev.attempts or 0) + 1
        ev.save(update_fields=["status", "locked_at", "attempts", "updated_at"])
        return ev


def _mark_done(ev: OutboxEvent) -> None:
    ev.status = OutboxEvent.Status.DONE
    ev.last_error = ""
    ev.save(update_fields=["status", "last_error", "updated_at"])


def _mark_retry(ev: OutboxEvent, err: str) -> None:
    # backoff: 2^attempts, capped 5 phút
    attempt = int(ev.attempts or 1)
    delay = min(300, 2 ** min(8, attempt))
    ev.status = OutboxEvent.Status.NEW
    ev.last_error = (err or "")[:2000]
    ev.available_at = timezone.now() + timezone.timedelta(seconds=delay)
    ev.save(update_fields=["status", "last_error", "available_at", "updated_at"])


def _mark_failed(ev: OutboxEvent, err: str) -> None:
    ev.status = OutboxEvent.Status.FAILED
    ev.last_error = (err or "")[:2000]
    ev.save(update_fields=["status", "last_error", "updated_at"])


def dispatch_forever(
    *,
    sleep_seconds: float = 0.5,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    lease_ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
) -> None:
    while True:
        ev = _lease_one(now=timezone.now(), lease_ttl_seconds=lease_ttl_seconds)
        if not ev:
            time.sleep(float(sleep_seconds or 0.5))
            continue

        handlers = get_handlers(ev.name)

        try:
            if not handlers:
                # không có handler thì đánh DONE để khỏi kẹt queue
                logger.warning("No handler for event: %s (id=%s)", ev.name, ev.id)
                _mark_done(ev)
                continue

            for h in handlers:
                h(ev)

            _mark_done(ev)

        except Exception as e:
            logger.exception("Event failed: id=%s name=%s attempts=%s", ev.id, ev.name, ev.attempts)

            if int(ev.attempts or 0) >= int(max_attempts or DEFAULT_MAX_ATTEMPTS):
                _mark_failed(ev, repr(e))
            else:
                _mark_retry(ev, repr(e))