# apps/os/action_runner.py
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from django.apps import apps
from django.db import IntegrityError, transaction
from django.utils import timezone


# =========================
# Helpers (safe + no hard dependency)
# =========================
def _get_model(app_label: str, model_name: str):
    try:
        return apps.get_model(app_label, model_name)
    except Exception:
        return None


def _safe_int(v, default: Optional[int] = None) -> Optional[int]:
    try:
        if v is None or v == "":
            return default
        return int(v)
    except Exception:
        return default


def _json_hash(data: Any) -> str:
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _now_iso() -> str:
    return timezone.now().isoformat()


def _emit_os_event_safe(
    *,
    tenant_id: int,
    name: str,
    entity: str,
    entity_id: int,
    payload: Optional[Dict[str, Any]] = None,
    company_id: Optional[int] = None,
    shop_id: Optional[int] = None,
    actor_id: Optional[int] = None,
) -> None:
    """
    Ưu tiên dùng apps.events.emit.emit_os_event nếu có.
    Fallback dùng OutboxEvent emit trực tiếp (apps.events.bus.emit_event).
    """
    payload = payload or {}

    # 1) try emit_os_event (nếu anh đã có)
    try:
        from apps.events.emit import emit_os_event  # type: ignore

        emit_os_event(
            tenant_id=int(tenant_id),
            name=str(name),
            entity=str(entity),
            entity_id=int(entity_id),
            payload=payload,
            company_id=company_id,
            shop_id=shop_id,
            actor_id=actor_id,
        )
        return
    except Exception:
        pass

    # 2) fallback emit_event (outbox)
    try:
        from apps.events.bus import emit_event, make_dedupe_key  # type: ignore

        dedupe = make_dedupe_key(
            name=str(name),
            tenant_id=int(tenant_id),
            entity=str(entity),
            entity_id=int(entity_id),
            extra={"h": _json_hash(payload)},
        )
        emit_event(
            tenant_id=int(tenant_id),
            company_id=company_id,
            shop_id=shop_id,
            actor_id=actor_id,
            name=str(name),
            version=1,
            dedupe_key=dedupe,
            payload={
                "entity": {"kind": entity, "id": int(entity_id)},
                **payload,
            },
        )
    except Exception:
        return


# =========================
# Action Result
# =========================
@dataclass
class ActionRunResult:
    ok: bool
    action_type: str
    message: str = ""
    created: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    emitted_event: bool = False
    notification_created: bool = False
    at: str = ""


# =========================
# Supported action types
# =========================
SUPPORTED_ACTIONS = {
    "task.create",
    "notification.create",
    "os.event.emit",
}


def _normalize_action(a: Dict[str, Any]) -> Dict[str, Any]:
    a = a or {}
    t = (a.get("type") or "").strip()
    payload = a.get("payload") if isinstance(a.get("payload"), dict) else {}
    return {
        "type": t,
        "payload": payload,
        "id": a.get("id"),
        "name": a.get("name"),
        "dedupe_key": (a.get("dedupe_key") or "").strip(),
        "meta": a.get("meta") if isinstance(a.get("meta"), dict) else {},
    }


def _make_action_dedupe(*, tenant_id: int, action: Dict[str, Any]) -> str:
    dk = (action.get("dedupe_key") or "").strip()
    if dk:
        return dk
    base = {
        "tenant_id": int(tenant_id),
        "type": action.get("type"),
        "payload": action.get("payload") or {},
    }
    return _json_hash(base)


# =========================
# Executors
# =========================
def _exec_task_create(
    *,
    tenant_id: int,
    payload: Dict[str, Any],
    actor_id: Optional[int] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    WorkItem = _get_model("work", "WorkItem")
    if not WorkItem:
        return False, "Không tìm thấy model WorkItem (apps.work.WorkItem)", None

    title = (payload.get("title") or "").strip()
    if not title:
        return False, "Thiếu title cho task.create", None

    company_id = _safe_int(payload.get("company_id"))
    project_id = _safe_int(payload.get("project_id"))
    shop_id = _safe_int(payload.get("shop_id"))

    description = (payload.get("description") or "").strip()
    priority = _safe_int(payload.get("priority"), 2) or 2
    wtype = (payload.get("type") or "task").strip().lower()

    target_type = (payload.get("target_type") or "").strip()
    target_id = _safe_int(payload.get("target_id"))

    assignee_id = _safe_int(payload.get("assignee_id"))
    requester_id = _safe_int(payload.get("requester_id"))

    visible_to_client = bool(payload.get("visible_to_client") or False)
    is_internal = bool(payload.get("is_internal") or True)

    obj = WorkItem(
        tenant_id=int(tenant_id),
        company_id=company_id,
        project_id=project_id,
        shop_id=shop_id,
        title=title,
        description=description,
        priority=int(priority),
        type=wtype,
        target_type=target_type,
        target_id=target_id,
        visible_to_client=visible_to_client,
        is_internal=is_internal,
        assignee_id=assignee_id,
        requester_id=requester_id,
        created_by_id=actor_id,
        status=getattr(WorkItem, "Status", None).TODO if hasattr(WorkItem, "Status") else "todo",
        position=1,
    )

    # để WorkItem.save() bắn outbox event có actor_id (nếu code của anh dùng _actor)
    try:
        if actor_id:
            User = _get_model("accounts", "User") or _get_model("auth", "User")
            if User:
                u = User.objects.filter(id=int(actor_id)).first()
                if u:
                    setattr(obj, "_actor", u)
    except Exception:
        pass

    obj.save()

    return True, "Tạo task thành công", {"kind": "workitem", "id": int(obj.id)}


def _exec_notification_create(
    *,
    tenant_id: int,
    payload: Dict[str, Any],
    actor_id: Optional[int] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Ưu tiên gọi service create_notification (apps.os.notifications_service)
    fallback: tạo thẳng OSNotification nếu có.
    """
    tieu_de = (payload.get("tieu_de") or payload.get("title") or "").strip()
    noi_dung = (payload.get("noi_dung") or payload.get("body") or payload.get("detail") or "").strip()
    severity = (payload.get("severity") or payload.get("muc_do") or "info").strip().lower()

    target_role = (payload.get("target_role") or "").strip().lower()
    target_user_id = _safe_int(payload.get("target_user_id"))
    company_id = _safe_int(payload.get("company_id"))
    shop_id = _safe_int(payload.get("shop_id"))

    entity_kind = (payload.get("entity_kind") or payload.get("entity") or "").strip()
    entity_id = _safe_int(payload.get("entity_id"))

    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}

    # 1) service
    try:
        from apps.os.notifications_service import create_notification  # type: ignore

        obj = create_notification(
            tenant_id=int(tenant_id),
            target_role=target_role or None,
            target_user_id=target_user_id,
            severity=severity,
            tieu_de=tieu_de or "Thông báo",
            noi_dung=noi_dung or "",
            entity_kind=entity_kind or None,
            entity_id=entity_id,
            company_id=company_id,
            shop_id=shop_id,
            actor_id=actor_id,
            meta=meta,
        )
        if obj:
            return True, "Tạo notification thành công", {"kind": "os_notification", "id": int(obj.id)}
    except Exception:
        pass

    # 2) fallback model
    OSNotification = _get_model("os", "OSNotification")
    if not OSNotification:
        return False, "Không tìm thấy OSNotification (apps.os.models.OSNotification)", None

    obj = OSNotification.objects_all.create(
        tenant_id=int(tenant_id),
        target_role=target_role or "",
        target_user_id=target_user_id,
        severity=severity,
        status=getattr(OSNotification, "Status", None).NEW if hasattr(OSNotification, "Status") else "new",
        tieu_de=tieu_de or "Thông báo",
        noi_dung=noi_dung or "",
        entity_kind=entity_kind or "",
        entity_id=entity_id,
        company_id=company_id,
        shop_id=shop_id,
        actor_id=actor_id,
        meta=meta or {},
        created_at=timezone.now(),
    )
    return True, "Tạo notification thành công", {"kind": "os_notification", "id": int(obj.id)}


def _exec_os_event_emit(
    *,
    tenant_id: int,
    payload: Dict[str, Any],
    actor_id: Optional[int] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    payload:
      {
        "name": "os.decision.created",
        "entity": "tenant",
        "entity_id": 1,
        "company_id": ...,
        "shop_id": ...,
        "payload": {...}
      }
    """
    name = (payload.get("name") or "").strip()
    entity = (payload.get("entity") or "").strip()
    entity_id = _safe_int(payload.get("entity_id"))

    if not name or not entity or not entity_id:
        return False, "Thiếu name/entity/entity_id cho os.event.emit", None

    company_id = _safe_int(payload.get("company_id"))
    shop_id = _safe_int(payload.get("shop_id"))
    inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}

    _emit_os_event_safe(
        tenant_id=int(tenant_id),
        name=name,
        entity=entity,
        entity_id=int(entity_id),
        payload=inner,
        company_id=company_id,
        shop_id=shop_id,
        actor_id=actor_id,
    )
    return True, "Emit event thành công", {"kind": "event", "name": name}


# =========================
# Public API
# =========================
def run_actions(
    *,
    tenant_id: int,
    actions: List[Dict[str, Any]],
    actor_id: Optional[int] = None,
    company_id: Optional[int] = None,
    shop_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Production-ready:
    - Không crash nếu action sai/thiếu model
    - Idempotent bằng OSActionLog
    - Emit os.action.executed + tạo notification cho assignee (nếu payload có)
    """

    tenant_id = int(tenant_id)
    actions = actions or []

    OSActionLog = _get_model("os", "OSActionLog")  # optional
    results: List[Dict[str, Any]] = []

    for raw in actions:
        a = _normalize_action(raw)
        at = _now_iso()

        if not a["type"]:
            results.append(ActionRunResult(ok=False, action_type="", message="Action thiếu type", at=at).__dict__)
            continue

        if a["type"] not in SUPPORTED_ACTIONS:
            results.append(
                ActionRunResult(ok=False, action_type=a["type"], message="Action type không hỗ trợ", at=at).__dict__
            )
            continue

        dedupe = _make_action_dedupe(tenant_id=tenant_id, action=a)

        # ====== Idempotent gate (optional) ======
        if OSActionLog:
            existed = OSActionLog.objects_all.filter(tenant_id=tenant_id, dedupe_key=dedupe).first()
            if existed and getattr(existed, "status", "") in {"done", "success"}:
                results.append(
                    ActionRunResult(
                        ok=True,
                        action_type=a["type"],
                        message="Bỏ qua vì đã chạy trước đó (idempotent)",
                        created=getattr(existed, "result", None) or {},
                        emitted_event=False,
                        notification_created=False,
                        at=at,
                    ).__dict__
                )
                continue

        ok = False
        msg = ""
        created: Optional[Dict[str, Any]] = None
        err: Optional[str] = None

        # ====== Execute inside atomic (each action) ======
        try:
            with transaction.atomic():
                if a["type"] == "task.create":
                    ok, msg, created = _exec_task_create(tenant_id=tenant_id, payload=a["payload"], actor_id=actor_id)

                elif a["type"] == "notification.create":
                    ok, msg, created = _exec_notification_create(
                        tenant_id=tenant_id, payload=a["payload"], actor_id=actor_id
                    )

                elif a["type"] == "os.event.emit":
                    ok, msg, created = _exec_os_event_emit(tenant_id=tenant_id, payload=a["payload"], actor_id=actor_id)

                else:
                    ok, msg, created = False, "Action type không hợp lệ", None

                # write log (optional)
                if OSActionLog:
                    status = "done" if ok else "failed"
                    try:
                        OSActionLog.objects_all.update_or_create(
                            tenant_id=tenant_id,
                            dedupe_key=dedupe,
                            defaults={
                                "action_type": a["type"],
                                "status": status,
                                "result": created or {},
                                "last_error": "",
                                "updated_at": timezone.now(),
                            },
                        )
                    except Exception:
                        pass

        except Exception as e:
            ok = False
            msg = "Lỗi khi thực thi action"
            err = repr(e)
            if OSActionLog:
                try:
                    OSActionLog.objects_all.update_or_create(
                        tenant_id=tenant_id,
                        dedupe_key=dedupe,
                        defaults={
                            "action_type": a["type"],
                            "status": "failed",
                            "result": created or {},
                            "last_error": (repr(e) or "")[:2000],
                            "updated_at": timezone.now(),
                        },
                    )
                except Exception:
                    pass

        # ====== Emit os.action.executed (best-effort) ======
        emitted = False
        try:
            _emit_os_event_safe(
                tenant_id=tenant_id,
                name="os.action.executed",
                entity="action",
                entity_id=int(_safe_int(a.get("id"), 0) or 0),
                company_id=company_id,
                shop_id=shop_id,
                actor_id=actor_id,
                payload={
                    "type": a["type"],
                    "ok": bool(ok),
                    "message": msg,
                    "created": created or {},
                    "dedupe_key": dedupe,
                },
            )
            emitted = True
        except Exception:
            emitted = False

        # ====== Optional: notify assignee if action payload has assignee_id ======
        notif_created = False
        try:
            assignee_id = _safe_int((a.get("payload") or {}).get("assignee_id"))
            if assignee_id:
                _exec_notification_create(
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    payload={
                        "target_user_id": int(assignee_id),
                        "target_role": "",
                        "severity": "info",
                        "tieu_de": "Bạn có hành động mới từ OS",
                        "noi_dung": f"OS vừa chạy: {a['type']} ({'OK' if ok else 'FAIL'})",
                        "entity_kind": "action",
                        "entity_id": int(_safe_int(a.get("id"), 0) or 0),
                        "company_id": company_id,
                        "shop_id": shop_id,
                        "meta": {"action": a, "result": {"ok": ok, "message": msg}},
                    },
                )
                notif_created = True
        except Exception:
            notif_created = False

        results.append(
            ActionRunResult(
                ok=bool(ok),
                action_type=a["type"],
                message=msg,
                created=created,
                error=err,
                emitted_event=emitted,
                notification_created=notif_created,
                at=at,
            ).__dict__
        )

    return {
        "ok": True,
        "tenant_id": int(tenant_id),
        "count": len(results),
        "items": results,
        "generated_at": _now_iso(),
    }