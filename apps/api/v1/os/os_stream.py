from __future__ import annotations

import json
import time
from typing import Any, Dict, Iterable

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, StreamingHttpResponse
from django.utils import timezone

from apps.api.v1.insight import _get_tenant_id


def _safe_import_outbox_model():
    candidates = [
        ("apps.events.models", "OutboxEvent"),
        ("apps.events.models", "Event"),
        ("apps.core.models", "OutboxEvent"),
    ]
    for mod, name in candidates:
        try:
            m = __import__(mod, fromlist=[name])
            return getattr(m, name)
        except Exception:
            continue
    return None


OutboxModel = _safe_import_outbox_model()


def _sse_pack(event: str, data: Dict[str, Any]) -> bytes:
    msg = f"event: {event}\n" f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    return msg.encode("utf-8")


@login_required
def os_stream_sse(request: HttpRequest):
    tenant_id = _get_tenant_id(request)
    if not tenant_id:
        resp = StreamingHttpResponse(
            iter([_sse_pack("error", {"message": "Thiếu tenant_id"})]),
            content_type="text/event-stream",
        )
        resp["Cache-Control"] = "no-cache"
        resp["X-Accel-Buffering"] = "no"
        return resp

    tenant_id = int(tenant_id)

    try:
        last_id = int(request.GET.get("last_id") or 0)
    except Exception:
        last_id = 0

    def gen() -> Iterable[bytes]:
        nonlocal last_id

        yield _sse_pack("hello", {"ok": True, "tenant_id": tenant_id, "ts": timezone.now().isoformat()})

        while True:
            yield _sse_pack("ping", {"ts": timezone.now().isoformat()})

            if OutboxModel is None:
                time.sleep(5)
                continue

            try:
                qs = (
                    OutboxModel.objects_all.filter(tenant_id=tenant_id, id__gt=last_id)
                    .order_by("id")[:50]
                )
                for ev in qs:
                    last_id = int(getattr(ev, "id", last_id))
                    payload = getattr(ev, "payload", {}) or {}
                    name = getattr(ev, "name", "event")
                    created_at = getattr(ev, "created_at", None)

                    yield _sse_pack(
                        "event",
                        {
                            "id": last_id,
                            "name": str(name),
                            "tenant_id": tenant_id,
                            "created_at": created_at.isoformat() if created_at else None,
                            "payload": payload,
                        },
                    )
            except Exception as e:
                yield _sse_pack("error", {"message": str(e)})

            time.sleep(5)

    resp = StreamingHttpResponse(gen(), content_type="text/event-stream; charset=utf-8")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"
    return resp