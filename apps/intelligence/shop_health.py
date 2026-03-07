# apps/intelligence/shop_health.py
from __future__ import annotations

from typing import Any, Dict

from django.db import transaction

from apps.events.bus import emit_event, make_dedupe_key

from .health_score import compute_shop_health


def evaluate_and_emit_shop_health(*, tenant_id: int, shop_id: int, actor_id: int | None = None) -> Dict[str, Any]:
    """
    Compute health + emit event (safe: on_commit).
    Event name: shop.health.updated
    """
    result = compute_shop_health(tenant_id=tenant_id, shop_id=shop_id)

    score = int(result["score"]["score"])
    level = str(result["score"]["level"])

    event_name = "shop.health.updated"
    dedupe = make_dedupe_key(
        name=event_name,
        tenant_id=tenant_id,
        entity="shop",
        entity_id=shop_id,
        extra={"score": score, "level": level, "generated_at": result.get("generated_at", "")},
    )

    payload = {
        "tenant_id": tenant_id,
        "shop_id": shop_id,
        "score": score,
        "level": level,
        "alerts": result.get("alerts", []),
        "metrics": result.get("metrics", {}),
        "generated_at": result.get("generated_at", ""),
    }

    def _emit():
        emit_event(
            tenant_id=tenant_id,
            company_id=None,
            shop_id=shop_id,
            actor_id=actor_id,
            name=event_name,
            version=1,
            dedupe_key=dedupe,
            payload=payload,
        )

    # safe emit after DB commit (avoid phantom event)
    try:
        transaction.on_commit(_emit)
    except Exception:
        _emit()

    return result