# apps/events/bus.py
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable, Dict, List, Optional

from django.db import IntegrityError
from django.utils import timezone

from apps.events.models import OutboxEvent

logger = logging.getLogger(__name__)

Handler = Callable[[OutboxEvent], None]

# event_name -> list handlers
_REGISTRY: Dict[str, List[Handler]] = {}


def register(name: str, handler: Handler) -> None:
    """
    FINAL:
    - chống register trùng (idempotent)
    """
    name = (name or "").strip()
    if not name or handler is None:
        return

    arr = _REGISTRY.setdefault(name, [])
    # dedupe theo identity (function object)
    if handler in arr:
        return
    arr.append(handler)


def get_handlers(name: str) -> List[Handler]:
    return list(_REGISTRY.get((name or "").strip(), []))


def make_dedupe_key(
    *,
    name: str,
    tenant_id: int,
    entity: str,
    entity_id: int,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    base = {
        "name": (name or "").strip(),
        "tenant_id": int(tenant_id or 0),
        "entity": (entity or "").strip(),
        "entity_id": int(entity_id or 0),
        "extra": extra or {},
    }
    raw = json.dumps(base, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def emit_event(
    *,
    tenant_id: int,
    company_id: Optional[int],
    shop_id: Optional[int],
    actor_id: Optional[int],
    name: str,
    version: int = 1,
    dedupe_key: str = "",
    payload: Optional[Dict[str, Any]] = None,
    delay_seconds: int = 0,
) -> Optional[int]:
    """
    Emit = ghi OutboxEvent (DB).
    Khuyến nghị: gọi trong transaction.on_commit() để tránh phantom event.
    """
    name = (name or "").strip()
    if not name:
        return None

    available_at = timezone.now() + timezone.timedelta(seconds=max(0, int(delay_seconds or 0)))

    data = dict(
        tenant_id=int(tenant_id),
        company_id=int(company_id) if company_id else None,
        shop_id=int(shop_id) if shop_id else None,
        actor_id=int(actor_id) if actor_id else None,
        name=name,
        version=int(version or 1),
        dedupe_key=(dedupe_key or "").strip(),
        payload=payload or {},
        status=OutboxEvent.Status.NEW,
        available_at=available_at,
    )

    try:
        ev = OutboxEvent.objects_all.create(**data)
        return int(ev.id)
    except IntegrityError:
        # duplicate dedupe_key -> ignore
        return None
    except Exception:
        logger.exception("emit_event failed: name=%s tenant=%s", name, tenant_id)
        return None