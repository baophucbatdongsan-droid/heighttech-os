# apps/notifications/handlers.py
from __future__ import annotations

from typing import Any, Dict, Optional

from apps.events.bus import make_dedupe_key
from apps.events.models import OutboxEvent
from apps.notifications.service import tao_thong_bao


def _level_for_event(name: str, payload: Dict[str, Any]) -> str:
    n = (name or "").lower()
    p = payload or {}

    if "failed" in n or "error" in n:
        return "critical"

    if name == "work.item.transitioned":
        to_status = str(p.get("to_status") or p.get("to") or "").strip().lower()
        if to_status == "blocked":
            return "warning"

    if "blocked" in str(p.get("status", "")).lower():
        return "warning"

    return "info"


def _tieu_de(name: str) -> str:
    if name == "work.item.created":
        return "Tạo công việc"
    if name == "work.item.updated":
        return "Cập nhật công việc"
    if name == "work.item.transitioned":
        return "Chuyển trạng thái"
    if name == "work.item.commented":
        return "Bình luận công việc"
    if name == "work.item.assigned":
        return "Giao việc"
    if name.startswith("os."):
        return "Cập nhật hệ điều hành"
    return "Thông báo hệ thống"


def _noi_dung(name: str, payload: Dict[str, Any]) -> str:
    p = payload or {}

    if name in {"work.item.created", "work.item.updated"}:
        wid = p.get("id")
        title = (p.get("title") or "").strip()
        st = (p.get("status") or "").strip()
        return f"#{wid} {title} ({st})".strip()

    if name == "work.item.transitioned":
        wid = p.get("id")
        frm = p.get("from_status") or p.get("from")
        to = p.get("to_status") or p.get("to")
        return f"#{wid} {frm} → {to}".strip()

    if name == "work.item.commented":
        wid = p.get("work_item_id") or p.get("id")
        body = (p.get("body") or "").strip()
        if len(body) > 120:
            body = body[:117] + "..."
        return f"#{wid} {body}".strip()

    if name == "work.item.assigned":
        wid = p.get("id") or p.get("work_item_id")
        assignee_id = p.get("assignee_id")
        title = (p.get("title") or "").strip()
        return f"#{wid} {title} → assignee #{assignee_id}".strip()

    return (p.get("message") or p.get("summary") or name).strip()


def _target_user_id_for_event(name: str, payload: Dict[str, Any]) -> Optional[int]:
    p = payload or {}

    if name == "work.item.assigned":
        try:
            aid = p.get("assignee_id")
            return int(aid) if aid else None
        except Exception:
            return None

    return None


def on_outbox_event_to_notification(ev: OutboxEvent) -> None:
    name = (ev.name or "").strip()
    if not name:
        return

    if not (name.startswith("work.") or name.startswith("os.")):
        return

    payload: Dict[str, Any] = ev.payload or {}

    tenant_id = int(getattr(ev, "tenant_id_id", None) or ev.tenant_id)
    company_id = getattr(ev, "company_id_id", None) or getattr(ev, "company_id", None)
    shop_id = getattr(ev, "shop_id_id", None) or getattr(ev, "shop_id", None)
    actor_id = getattr(ev, "actor_id", None)

    # targeted nếu là assign, còn lại beta vẫn broadcast
    user_id: Optional[int] = _target_user_id_for_event(name, payload)

    level = _level_for_event(name, payload)

    dedupe = make_dedupe_key(
        name="notification",
        tenant_id=tenant_id,
        entity="outbox",
        entity_id=int(ev.id),
        extra={"name": name},
    )

    doi_tuong_loai = ""
    doi_tuong_id = None

    wid = payload.get("id") or payload.get("work_item_id") or payload.get("workitem_id")
    if wid:
        doi_tuong_loai = "workitem"
        try:
            doi_tuong_id = int(wid)
        except Exception:
            doi_tuong_id = None

    tao_thong_bao(
        tenant_id=tenant_id,
        company_id=company_id,
        shop_id=shop_id,
        actor_id=actor_id,
        user_id=user_id,
        level=level,
        tieu_de=_tieu_de(name),
        noi_dung=_noi_dung(name, payload),
        doi_tuong_loai=doi_tuong_loai,
        doi_tuong_id=doi_tuong_id,
        dedupe_key=dedupe,
        meta={
            "event_id": ev.id,
            "event_name": name,
            "payload": payload,
            "target_user_id": user_id,
        },
    )
    
