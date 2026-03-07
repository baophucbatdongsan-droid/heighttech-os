# apps/core/audit.py
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Optional, Tuple

from django.conf import settings
from django.db import transaction


# =====================================================
# FLAGS
# =====================================================

_AUDIT_DISABLED: ContextVar[bool] = ContextVar("AUDIT_DISABLED", default=False)
_AUDIT_SIGNALS_DISABLED: ContextVar[bool] = ContextVar("AUDIT_SIGNALS_DISABLED", default=False)


def _audit_enabled() -> bool:
    """
    Single source of truth:
    - settings.AUDIT_ENABLED = False => audit NO-OP tuyệt đối (đặc biệt cho test)
    """
    return bool(getattr(settings, "AUDIT_ENABLED", True))


def is_audit_disabled() -> bool:
    """
    Audit bị tắt nếu:
    - AUDIT_ENABLED=False
    - context flags bật
    """
    try:
        if not _audit_enabled():
            return True
        return bool(_AUDIT_DISABLED.get()) or bool(_AUDIT_SIGNALS_DISABLED.get())
    except Exception:
        # fail-safe: có lỗi thì coi như tắt audit
        return True


@contextmanager
def audit_disabled():
    token = _AUDIT_DISABLED.set(True)
    try:
        yield
    finally:
        _AUDIT_DISABLED.reset(token)


def audit_signals_disabled() -> bool:
    """
    Backward compatible helper cho signals cũ.
    """
    try:
        if not _audit_enabled():
            return True
        return bool(_AUDIT_SIGNALS_DISABLED.get())
    except Exception:
        return True


@contextmanager
def disable_audit_signals():
    """
    Dùng khi muốn tắt audit trong signals (bulk import).
    """
    token = _AUDIT_SIGNALS_DISABLED.set(True)
    try:
        yield
    finally:
        _AUDIT_SIGNALS_DISABLED.reset(token)


# =====================================================
# JSON SAFE
# =====================================================

def _jsonify_value(v: Any) -> Any:
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
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {str(k): jsonify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [jsonify(v) for v in list(obj)]
    return _jsonify_value(obj)


# =====================================================
# SNAPSHOT / DIFF
# =====================================================

def make_snapshot(obj: Any, fields: list[str]) -> Dict[str, Any]:
    """
    ✅ BACKWARD COMPATIBLE:
    apps/api/v1/imports.py đang import make_snapshot => phải giữ.
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
        fields = [f.name for f in obj._meta.concrete_fields]
    except Exception:
        fields = []
    return make_snapshot(obj, fields)


def diff_changed_fields(
    before: Dict[str, Any],
    after: Dict[str, Any],
) -> Tuple[Dict[str, Any], list[str]]:
    """
    Return: (diff_map, changed_fields_list)
    diff_map[k] = {"before":..., "after":...}
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
# TENANT RESOLVE
# =====================================================

def _fallback_current_tenant_id() -> Optional[int]:
    """
    Lấy tenant_id từ tenant_context (an toàn cho shell + request).
    """
    try:
        from apps.core.tenant_context import get_current_tenant
        t = get_current_tenant()
        tid = getattr(t, "id", None) or getattr(t, "pk", None)
        if tid:
            return int(tid)
    except Exception:
        pass
    return None


def _resolve_tenant_id(instance: Any) -> Optional[int]:
    """
    Resolve tenant_id theo chain phổ biến, tránh query.
    """
    if not instance:
        return None

    for chain in [
        ("tenant_id",),
        ("tenant", "id"),
        ("company", "tenant_id"),
        ("brand", "company", "tenant_id"),
        ("shop", "brand", "company", "tenant_id"),
        ("project", "tenant_id"),
    ]:
        try:
            cur = instance
            for a in chain:
                cur = getattr(cur, a, None)
                if cur is None:
                    break
            if cur:
                return int(cur)
        except Exception:
            continue

    return None


# =====================================================
# CORE LOG
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
    Production-safe audit:
    - AUDIT_ENABLED=False => NO-OP tuyệt đối
    - Ghi sau commit
    - Không bao giờ làm crash business flow
    """
    if is_audit_disabled():
        return

    oid = str(object_id or "")

    # resolve tenant_id
    if tenant_id is None:
        tenant_id = _fallback_current_tenant_id()

    # không có tenant => bỏ qua (đỡ FK fail)
    if not tenant_id:
        return

    def _write():
        try:
            from apps.core.models import AuditLog

            app_label = model.split(".", 1)[0] if "." in model else ""
            model_name = model.split(".", 1)[-1] if model else ""

            payload: Dict[str, Any] = {
                "tenant_id": tenant_id,
                "actor": actor if getattr(actor, "is_authenticated", False) else None,
                "action": action,
                "app_label": app_label,
                "model_name": model_name,
                "object_pk": oid,
                "before": jsonify(before) if before is not None else None,
                "after": jsonify(after) if after is not None else None,
                "meta": jsonify(meta or {}),
                "changed_fields": jsonify(changed_fields or []),
            }

            # NOTE: AuditLog model bạn có field "note" không?
            # nếu có thì set, nếu không thì bỏ qua
            try:
                field_names = {f.name for f in AuditLog._meta.get_fields()}
                if "note" in field_names:
                    payload["note"] = note or ""
            except Exception:
                pass

            AuditLog.objects.create(**payload)
        except Exception:
            return

    transaction.on_commit(_write)


# =====================================================
# WRAPPERS
# =====================================================

def log_create(instance: Any, actor: Any = None, note: str = "") -> None:
    if is_audit_disabled():
        return

    model = f"{instance._meta.app_label}.{instance.__class__.__name__}"
    tid = _resolve_tenant_id(instance) or _fallback_current_tenant_id()

    log_change(
        actor=actor,
        action="create",
        model=model,
        object_id=getattr(instance, "pk", ""),
        before=None,
        after=make_snapshot_concrete(instance),
        note=note,
        tenant_id=tid,
    )


def log_update(
    instance: Any,
    before: Dict[str, Any],
    actor: Any = None,
    note: str = "",
) -> None:
    if is_audit_disabled():
        return

    model = f"{instance._meta.app_label}.{instance.__class__.__name__}"
    tid = _resolve_tenant_id(instance) or _fallback_current_tenant_id()

    after = make_snapshot_concrete(instance)
    diff, changed = diff_changed_fields(before, after)

    log_change(
        actor=actor,
        action="update",
        model=model,
        object_id=getattr(instance, "pk", ""),
        before=before,
        after=after,
        note=note,
        tenant_id=tid,
        meta=diff,
        changed_fields=changed,
    )


def log_delete(instance: Any, actor: Any = None, note: str = "") -> None:
    if is_audit_disabled():
        return

    model = f"{instance._meta.app_label}.{instance.__class__.__name__}"
    tid = _resolve_tenant_id(instance) or _fallback_current_tenant_id()

    log_change(
        actor=actor,
        action="delete",
        model=model,
        object_id=getattr(instance, "pk", ""),
        before=make_snapshot_concrete(instance),
        after=None,
        note=note,
        tenant_id=tid,
    )