# apps/core/audit.py
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Optional, Tuple, List

from django.db import transaction


# =====================================================
# TẮT AUDIT (dùng cho migrate/backfill/bulk script)
# + BACKWARD COMPATIBILITY cho signals cũ
# =====================================================

_AUDIT_DISABLED: ContextVar[bool] = ContextVar("AUDIT_DISABLED", default=False)
_audit_signals_disabled: ContextVar[bool] = ContextVar("audit_signals_disabled", default=False)


def is_audit_disabled() -> bool:
    """
    Trả về True nếu audit đang bị tắt trong context hiện tại.
    (Gồm cả flag mới và flag signals cũ)
    """
    try:
        return bool(_AUDIT_DISABLED.get()) or bool(_audit_signals_disabled.get())
    except Exception:
        return False


@contextmanager
def audit_disabled():
    """
    Tắt audit tạm thời để:
    - tránh log đôi khi bạn tự log thủ công
    - tránh audit trong migrate/backfill

    Ví dụ:
        with audit_disabled():
            obj.save()
    """
    token = _AUDIT_DISABLED.set(True)
    try:
        yield
    finally:
        _AUDIT_DISABLED.reset(token)


def audit_signals_disabled() -> bool:
    """
    Dùng trong signals cũ:
        if audit_signals_disabled():
            return
    """
    try:
        return bool(_audit_signals_disabled.get())
    except Exception:
        return False


@contextmanager
def disable_audit_signals():
    """
    Dùng khi muốn tắt audit trong signals (ví dụ bulk import).
    """
    token = _audit_signals_disabled.set(True)
    try:
        yield
    finally:
        _audit_signals_disabled.reset(token)


# =====================================================
# CHUYỂN DỮ LIỆU SANG JSON-SAFE (KHÔNG NỔ JSONField)
# =====================================================

def _jsonify_value(v: Any) -> Any:
    """
    Convert value -> JSON-safe types.
    - datetime/date/time -> isoformat
    - Decimal -> float (fallback: str)
    - UUID -> str
    - Django model instance -> pk (str)
    """
    from datetime import date, datetime, time
    from decimal import Decimal
    from uuid import UUID

    if v is None:
        return None

    if isinstance(v, (str, int, float, bool)):
        return v

    if isinstance(v, (datetime, date, time)):
        return v.isoformat()

    if isinstance(v, Decimal):
        try:
            return float(v)
        except Exception:
            return str(v)

    if isinstance(v, UUID):
        return str(v)

    # Django model instance -> pk
    if hasattr(v, "_meta") and hasattr(v, "pk"):
        return str(getattr(v, "pk", "") or "")

    return v


def jsonify(obj: Any) -> Any:
    """
    Đệ quy convert dict/list/tuple/set -> JSON-safe.
    """
    if obj is None:
        return None

    if isinstance(obj, dict):
        return {str(k): jsonify(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple, set)):
        return [jsonify(v) for v in list(obj)]

    return _jsonify_value(obj)


# =====================================================
# SNAPSHOT (CHỤP DỮ LIỆU MODEL)
# =====================================================

def make_snapshot(obj: Any, fields: list[str]) -> Dict[str, Any]:
    """
    Snapshot object theo list fields (an toàn, không query).
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
    Snapshot theo concrete_fields (không dính m2m/related), phù hợp cho Audit.
    """
    if obj is None:
        return {}
    try:
        fields = [f.name for f in obj._meta.concrete_fields]  # type: ignore[attr-defined]
    except Exception:
        fields = []
    return make_snapshot(obj, fields)


def diff_changed_fields(before: Dict[str, Any], after: Dict[str, Any]) -> Tuple[Dict[str, Any], list[str]]:
    """
    Tạo diff map + list field thay đổi (Level 9 dùng để filter nhanh).
    """
    before = before or {}
    after = after or {}

    changed: list[str] = []
    diff: Dict[str, Any] = {}

    keys = set(before.keys()) | set(after.keys())
    for k in sorted(keys):
        if before.get(k) != after.get(k):
            changed.append(k)
            diff[k] = {"before": before.get(k), "after": after.get(k)}

    return diff, changed


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
    Lấy meta request từ middleware (thread-local).
    """
    try:
        from apps.core.middleware import get_current_request_meta  # type: ignore
        meta = get_current_request_meta() or {}
        return meta if isinstance(meta, dict) else {}
    except Exception:
        return {}


def _get_actor(actor: Any = None) -> Any:
    """
    Ưu tiên actor truyền vào. Nếu None thì lấy từ middleware thread-local.
    """
    if actor is not None:
        return actor
    try:
        from apps.core.middleware import get_current_user  # type: ignore
        return get_current_user()
    except Exception:
        return None


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
    Resolve tenant_id theo chain phổ biến (không query):
    - instance.tenant_id / instance.tenant.id
    - instance.company.tenant_id
    - instance.brand.company.tenant_id
    - instance.shop.brand.company.tenant_id
    """
    if not instance:
        return None

    for attr_chain in [
        ("tenant_id",),
        ("tenant", "id"),
        ("company", "tenant_id"),
        ("brand", "company", "tenant_id"),
        ("shop", "brand", "company", "tenant_id"),
    ]:
        try:
            cur = instance
            for a in attr_chain:
                cur = getattr(cur, a, None)
                if cur is None:
                    break
            if cur:
                return int(cur)
        except Exception:
            continue

    return None


# =====================================================
# GHI AUDITLOG (SINGLE SOURCE OF TRUTH)
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
    meta: Optional[Dict[str, Any]] = None,
    changed_fields: Optional[list[str]] = None,
) -> None:
    """
    Ghi AuditLog sau commit để tránh log “ảo”.

    action: create/update/delete/export_csv/bulk_update/request/exception/...
    model: "app.Model" (vd: "projects.Project")
    object_id: pk hoặc id logic (vd: "export", "bulk", request_id)
    """
    if is_audit_disabled():
        return

    oid = str(object_id or "")

    # tenant fallback nếu caller không truyền
    if tenant_id is None:
        tenant_id = _fallback_current_tenant_id()

    def _write():
        from apps.core.models import AuditLog  # import tại chỗ tránh circular

        req_meta = _get_request_meta()
        _actor = _get_actor(actor)

        payload: Dict[str, Any] = {
            "actor": _actor if getattr(_actor, "is_authenticated", False) else None,
            "action": action,
            "before": jsonify(before) if before is not None else None,
            "after": jsonify(after) if after is not None else None,
        }

        # tenant FK
        if _has_model_field(AuditLog, "tenant"):
            payload["tenant_id"] = tenant_id

        # model identity
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

        # request meta (giữ ổn định)
        if _has_model_field(AuditLog, "ip_address"):
            ip = req_meta.get("ip")
            payload["ip_address"] = (str(ip) if ip else None)

        if _has_model_field(AuditLog, "user_agent"):
            payload["user_agent"] = req_meta.get("user_agent") or None

        if _has_model_field(AuditLog, "referer"):
            payload["referer"] = req_meta.get("referer") or None

        if _has_model_field(AuditLog, "path"):
            payload["path"] = req_meta.get("path") or ""

        if _has_model_field(AuditLog, "method"):
            payload["method"] = req_meta.get("method") or ""

        # ✅ Level 10.5: request_id / trace_id
        if _has_model_field(AuditLog, "request_id"):
            payload["request_id"] = req_meta.get("request_id") or ""

        if _has_model_field(AuditLog, "trace_id"):
            payload["trace_id"] = req_meta.get("trace_id") or ""

        # meta + changed_fields
        if _has_model_field(AuditLog, "meta"):
            payload["meta"] = jsonify(meta or {})

        if _has_model_field(AuditLog, "changed_fields"):
            payload["changed_fields"] = jsonify(changed_fields or [])

        if _has_model_field(AuditLog, "note"):
            payload["note"] = note or ""

        AuditLog.objects.create(**payload)

    # ✅ CỰC QUAN TRỌNG: chỉ ghi sau commit
    transaction.on_commit(_write)


# =====================================================
# WRAPPERS (dành cho signals / code)
# =====================================================

def log_create(instance: Any, actor: Any = None, after: Optional[Dict[str, Any]] = None, note: str = "") -> None:
    if is_audit_disabled():
        return
    model = f"{instance._meta.app_label}.{instance.__class__.__name__}"
    tid = _resolve_tenant_id(instance) or _fallback_current_tenant_id()
    _after = after if after is not None else make_snapshot_concrete(instance)

    log_change(
        actor=actor,
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
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    actor: Any = None,
    note: str = "",
) -> None:
    if is_audit_disabled():
        return
    model = f"{instance._meta.app_label}.{instance.__class__.__name__}"
    tid = _resolve_tenant_id(instance) or _fallback_current_tenant_id()
    _after = after if after is not None else make_snapshot_concrete(instance)

    log_change(
        actor=actor,
        action="update",
        model=model,
        object_id=getattr(instance, "pk", ""),
        before=before,
        after=_after,
        note=note,
        tenant_id=tid,
    )


def log_delete(instance: Any, before: Optional[Dict[str, Any]] = None, actor: Any = None, note: str = "") -> None:
    if is_audit_disabled():
        return
    model = f"{instance._meta.app_label}.{instance.__class__.__name__}"
    tid = _resolve_tenant_id(instance) or _fallback_current_tenant_id()
    _before = before if before is not None else make_snapshot_concrete(instance)

    log_change(
        actor=actor,
        action="delete",
        model=model,
        object_id=getattr(instance, "pk", ""),
        before=_before,
        after=None,
        note=note,
        tenant_id=tid,
    )