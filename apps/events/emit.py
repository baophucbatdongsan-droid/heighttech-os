# apps/events/emit.py
from __future__ import annotations

from typing import Any, Dict, Optional

from apps.events.bus import emit_event, make_dedupe_key
from apps.events.taxonomy import require_event
from apps.events.event_registry import is_valid_event


def emit_os_event(
    *,
    tenant_id: int,
    name: str,
    entity: str,
    entity_id: int,
    payload: Optional[Dict[str, Any]] = None,
    company_id: Optional[int] = None,
    shop_id: Optional[int] = None,
    actor_id: Optional[int] = None,
    extra_dedupe: Optional[Dict[str, Any]] = None,
) -> None:
    e = require_event(name)

    dedupe = make_dedupe_key(
        name=e.name,
        tenant_id=int(tenant_id),
        entity=(entity or "unknown"),
        entity_id=int(entity_id or 0),
        extra=extra_dedupe or {},
    )

    emit_event(
        tenant_id=int(tenant_id),
        company_id=company_id,
        shop_id=shop_id,
        actor_id=actor_id,
        name=e.name,
        version=int(e.version),
        dedupe_key=dedupe,
        payload=payload or {},
    )

    if not is_valid_event(name):
        raise ValueError(f"Invalid OS event: {name}")