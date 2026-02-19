# apps/core/audit.py
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Optional

from django.db import transaction


# =====================================================
# AUDIT DISABLE FLAG (for bulk import, backfill, scripts)
# =====================================================

_AUDIT_DISABLED: ContextVar[bool] = ContextVar("AUDIT_DISABLED", default=False)


@contextmanager
def audit_disabled():
    """
    Dùng để tắt audit trong signals khi bạn đã tự log thủ công (tránh log đôi).
    Example:
        with audit_disabled():
            obj.save()
    """
    token = _AUDIT_DISABLED.set(True)
    try:
        yield
    finally:
        _AUDIT_DISABLED.reset(token)


def _is_audit_disabled() -> bool:
    try:
        return bool(_AUDIT_DISABLED.get())
    except Exception:
        return False


# =====================================================
# JSON SAFE
# =====================================================

def _jsonify_value(v: Any) -> Any:
    """
    Convert value -> JSON safe types.
    - Decimal -> float
    - date/datetime -> isoformat
    - UUID -> str
    - Model instance -> pk (str)
    """
    try:
        from decimal import Decimal
        from datetime import date, datetime
        from uuid import UUID

        if v is None:
            return None

        if isinstance(v, Decimal):
            return float(v)

        if isinstance(v, (date, datetime)):
            return v.isoformat()

        if isinstance(v, UUID):
            return str(v)

        # Django model instance -> pk
        if hasattr(v, "_meta") and hasattr(v, "pk"):
            return str(getattr(v, "pk", "") or "")
    except Exception:
        pass

    return v


def _jsonify_obj(obj: Any) -> Any:
    """
    Đệ quy convert dict/list/tuple/set -> JSON safe.
    """
    if obj is None:
        return None

    if isinstance(obj, dict):
        return {str(k): _jsonify_obj(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple, set)):
        return [_jsonify_obj(v) for v in obj]

    return _jsonify_value(obj)


# =====================================================
# SNAPSHOT HELPERS
# =====================================================

def make_snapshot(obj: Any, fields: list[str]) -> Dict[str, Any]:
    """
    Snapshot object theo list fields (an toàn).
    """
    if obj is None:
        return {}

    data: Dict[str, Any] = {}
    for f in fields:
        try:
            data[f] = _jsonify_value(getattr(obj, f, None))
        except Exception:
            data[f] = None

    data["pk"] = str(getattr(obj, "pk", "") or "")
    return data


def make_snapshot_concrete(obj: Any) -> Dict[str, Any]:
    """
    Snapshot theo concrete_fields (không dính m2m/related).
    """
    if obj is None:
        return {}
    try:
        fields = [f.name for f in obj._meta.concrete_fields]  # type: ignore[attr-defined]
    except Exception:
        fields = []
    return make_snapshot(obj, fields)


# =====================================================
# INTERNAL HELPERS
# =====================================================

def _has_model_field(model_cls, field_name: str) -> bool:
    try:
        return any(f.name == field_name for f in model_cls._meta.get_fields())
    except Exception:
        return False


def _get_request_meta() -> Dict[str, Any]:
    """
    Lấy meta từ middleware nếu có.
    """
    try:
        from apps.core.middleware import get_current_request_meta  # type: ignore
        meta = get_current_request_meta() or {}
        return meta if isinstance(meta, dict) else {}
    except Exception:
        return {}


def _get_actor_from_middleware(actor: Any = None) -> Any:
    """
    Ưu tiên actor truyền vào, nếu None thì lấy từ thread-local middleware.
    """
    if actor is not None:
        return actor
    try:
        from apps.core.middleware import get_current_user  # type: ignore
        return get_current_user()
    except Exception:
        return None


def _meta_get(meta: Dict[str, Any], key: str, default: str = "") -> str:
    v = meta.get(key)
    return str(v) if v is not None else default


def _fallback_current_tenant_id() -> Optional[int]:
    """
    Fallback tenant_id nếu caller không truyền.
    Ưu tiên:
    - request.tenant_id (middleware)
    - contextvar get_current_tenant()
    """
    try:
        from apps.core.middleware import get_current_tenant_id  # type: ignore
        tid = get_current_tenant_id()
        if tid:
            return int(tid)
    except Exception:
        pass

    try:
        from apps.core.tenant_context import get_current_tenant  # type: ignore
        t = get_current_tenant()
        tid = getattr(t, "id", None) or getattr(t, "pk", None)
        if tid:
            return int(tid)
    except Exception:
        pass

    return None


def _resolve_tenant_id(instance: Any) -> Optional[int]:
    """
    Resolve tenant_id theo chain phổ biến:
    - instance.tenant_id / instance.tenant.id
    - instance.company.tenant_id
    - instance.brand.company.tenant_id
    - instance.shop.brand.company.tenant_id

    Ưu tiên dùng dữ liệu đang có (không query).
    """
    if not instance:
        return None

    # 1) instance.tenant_id
    try:
        tid = getattr(instance, "tenant_id", None)
        if tid:
            return int(tid)
    except Exception:
        pass

    # 2) instance.tenant (FK object)
    try:
        t = getattr(instance, "tenant", None)
        if t is not None:
            tid = getattr(t, "id", None) or getattr(t, "pk", None)
            if tid:
                return int(tid)
    except Exception:
        pass

    # 3) instance.company.tenant_id
    try:
        c = getattr(instance, "company", None)
        if c is not None:
            tid = getattr(c, "tenant_id", None)
            if tid:
                return int(tid)
    except Exception:
        pass

    # 4) instance.brand.company.tenant_id
    try:
        b = getattr(instance, "brand", None)
        if b is not None:
            c = getattr(b, "company", None)
            if c is not None:
                tid = getattr(c, "tenant_id", None)
                if tid:
                    return int(tid)
    except Exception:
        pass

    # 5) instance.shop.brand.company.tenant_id
    try:
        s = getattr(instance, "shop", None)
        if s is not None:
            b = getattr(s, "brand", None)
            if b is not None:
                c = getattr(b, "company", None)
                if c is not None:
                    tid = getattr(c, "tenant_id", None)
                    if tid:
                        return int(tid)
    except Exception:
        pass

    return None


# =====================================================
# CORE WRITER (single source of truth)
# =====================================================

def log_change(
    *,
    actor: Any = None,
    action: str,
    model: str,
    object_id: Any,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    note: str = "",
    tenant_id: Optional[int] = None,
) -> None:
    """
    Ghi AuditLog sau commit để tránh log “ảo”.
    Support schema cũ (app_label, model_name, object_pk, meta) + tenant (nếu có).
    Support thêm schema mới (model/object_id/note) nếu sau này bạn mở rộng.
    """
    if _is_audit_disabled():
        return

    oid = str(object_id or "")

    # tenant fallback nếu caller không truyền
    if tenant_id is None:
        tenant_id = _fallback_current_tenant_id()

    def _write():
        from apps.core.models import AuditLog  # local import tránh circular

        meta = _get_request_meta()
        _actor = _get_actor_from_middleware(actor)

        payload: Dict[str, Any] = {
            "actor": _actor if getattr(_actor, "is_authenticated", False) else None,
            "action": action,
            "before": _jsonify_obj(before) if before is not None else None,
            "after": _jsonify_obj(after) if after is not None else None,
        }

        # tenant FK (nếu AuditLog có field tenant)
        if _has_model_field(AuditLog, "tenant"):
            payload["tenant_id"] = tenant_id

        # schema mới (nếu có)
        if _has_model_field(AuditLog, "model"):
            payload["model"] = model
        if _has_model_field(AuditLog, "object_id"):
            payload["object_id"] = oid
        if _has_model_field(AuditLog, "note"):
            payload["note"] = note or ""

        # schema cũ: app_label/model_name/object_pk
        if _has_model_field(AuditLog, "app_label") or _has_model_field(AuditLog, "model_name"):
            app_label = ""
            model_name = model
            if "." in model:
                app_label, model_name = model.split(".", 1)

            if _has_model_field(AuditLog, "app_label"):
                payload["app_label"] = app_label
            if _has_model_field(AuditLog, "model_name"):
                payload["model_name"] = model_name
            if _has_model_field(AuditLog, "object_pk"):
                payload["object_pk"] = oid

        # request meta
        if _has_model_field(AuditLog, "ip_address"):
            ip = _meta_get(meta, "ip")
            payload["ip_address"] = ip or None
        if _has_model_field(AuditLog, "user_agent"):
            ua = _meta_get(meta, "user_agent")
            payload["user_agent"] = ua or None
        if _has_model_field(AuditLog, "referer"):
            payload["referer"] = _meta_get(meta, "referer") or None
        if _has_model_field(AuditLog, "path"):
            payload["path"] = _meta_get(meta, "path") or ""
        if _has_model_field(AuditLog, "method"):
            payload["method"] = _meta_get(meta, "method") or ""

        AuditLog.objects.create(**payload)

    transaction.on_commit(_write)


# =====================================================
# WRAPPERS (signals-friendly)
# =====================================================

def log_create(instance: Any, actor: Any = None, after: Optional[Dict[str, Any]] = None, note: str = "") -> None:
    if _is_audit_disabled():
        return

    _actor = _get_actor_from_middleware(actor)
    model = f"{instance._meta.app_label}.{instance.__class__.__name__}"
    tid = _resolve_tenant_id(instance) or _fallback_current_tenant_id()

    _after = after if after is not None else make_snapshot_concrete(instance)

    log_change(
        actor=_actor,
        action="create",
        model=model,
        object_id=getattr(instance, "pk", ""),
        before=None,
        after=_after,
        note=note,
        tenant_id=tid,
    )


def log_update(
    instance: Any,
    before: Optional[Dict[str, Any]] = None,  # ✅ before positional OK
    after: Optional[Dict[str, Any]] = None,
    actor: Any = None,
    note: str = "",
) -> None:
    if _is_audit_disabled():
        return

    _actor = _get_actor_from_middleware(actor)
    model = f"{instance._meta.app_label}.{instance.__class__.__name__}"
    tid = _resolve_tenant_id(instance) or _fallback_current_tenant_id()

    _after = after if after is not None else make_snapshot_concrete(instance)

    log_change(
        actor=_actor,
        action="update",
        model=model,
        object_id=getattr(instance, "pk", ""),
        before=before,
        after=_after,
        note=note,
        tenant_id=tid,
    )


def log_delete(instance: Any, before: Optional[Dict[str, Any]] = None, actor: Any = None, note: str = "") -> None:
    if _is_audit_disabled():
        return

    _actor = _get_actor_from_middleware(actor)
    model = f"{instance._meta.app_label}.{instance.__class__.__name__}"
    tid = _resolve_tenant_id(instance) or _fallback_current_tenant_id()

    _before = before if before is not None else make_snapshot_concrete(instance)

    log_change(
        actor=_actor,
        action="delete",
        model=model,
        object_id=getattr(instance, "pk", ""),
        before=_before,
        after=None,
        note=note,
        tenant_id=tid,
    )
# apps/core/audit.py
from contextvars import ContextVar
from contextlib import contextmanager

_audit_signals_disabled: ContextVar[bool] = ContextVar("audit_signals_disabled", default=False)

def audit_signals_disabled() -> bool:
    return bool(_audit_signals_disabled.get())

@contextmanager
def disable_audit_signals():
    token = _audit_signals_disabled.set(True)
    try:
        yield
    finally:
        _audit_signals_disabled.reset(token)
