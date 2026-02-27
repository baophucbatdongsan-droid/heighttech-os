# apps/core/audit_signals.py
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID
from typing import Any, Dict, Optional, Tuple

from django.conf import settings
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.forms.models import model_to_dict

from apps.core.models import AuditLog
from apps.core.tenant_context import get_current_tenant


# ==========================================================
# CẤU HÌNH BỎ QUA MODEL HỆ THỐNG
# ==========================================================

# Các model Django hay ghi trong migrate/runserver mà mình KHÔNG audit
_SKIP_LABELS = {
    "core.auditlog",                 # tránh vòng lặp
    "admin.logentry",
    "sessions.session",
    "contenttypes.contenttype",
    "auth.permission",
    "authtoken.token",
    "migrations.migration",          # bảng django_migrations (nguyên nhân lỗi của bạn)
}

# Ngoài ra bỏ qua cả app_label hệ thống (tùy bạn mở rộng)
_SKIP_APP_LABELS = {
    "migrations",
    "contenttypes",
    "sessions",
    "admin",
}


# ==========================================================
# JSON SAFE (đẩy vào JSONField không nổ)
# ==========================================================

def _to_jsonable(value: Any) -> Any:
    """
    Chuyển object Python/Django về dạng JSON-safe.
    - datetime/date/time -> isoformat()
    - Decimal -> float
    - UUID -> str
    - Model -> pk
    - set/tuple -> list
    - dict/list -> recursive
    """
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, (datetime, date, time)):
        return value.isoformat()

    if isinstance(value, Decimal):
        try:
            return float(value)
        except Exception:
            return str(value)

    if isinstance(value, UUID):
        return str(value)

    # Django model instance -> pk
    if hasattr(value, "_meta") and hasattr(value, "pk"):
        return getattr(value, "pk", None)

    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(v) for v in list(value)]

    # fallback: string
    return str(value)


def _snapshot_instance(instance) -> Dict[str, Any]:
    """
    Snapshot an toàn: dùng model_to_dict, rồi convert JSON-safe.
    """
    try:
        data = model_to_dict(instance)
    except Exception:
        # fallback nếu model_to_dict fail
        data = {}
        for k, v in getattr(instance, "__dict__", {}).items():
            if k.startswith("_"):
                continue
            data[k] = v

    return _to_jsonable(data)


def _diff(before: Dict[str, Any], after: Dict[str, Any]) -> Tuple[Dict[str, Any], list]:
    """
    Tạo diff đơn giản + list field thay đổi.
    """
    changed = []
    diff_map: Dict[str, Any] = {}

    keys = set(before.keys()) | set(after.keys())
    for k in sorted(keys):
        if before.get(k) != after.get(k):
            changed.append(k)
            diff_map[k] = {"before": before.get(k), "after": after.get(k)}

    return diff_map, changed


def _should_skip(sender, instance) -> bool:
    """
    Bỏ qua model hệ thống + chính AuditLog.
    """
    try:
        label = sender._meta.label_lower
        app_label = sender._meta.app_label
    except Exception:
        return True

    if label in _SKIP_LABELS:
        return True

    if app_label in _SKIP_APP_LABELS:
        return True

    # Nếu sender là AuditLog -> bỏ qua
    if isinstance(instance, AuditLog):
        return True

    return False


# ==========================================================
# LƯU BEFORE SNAPSHOT TRONG MEMORY (CHO UPDATE)
# ==========================================================

@receiver(pre_save)
def _audit_pre_save(sender, instance, **kwargs):
    if _should_skip(sender, instance):
        return

    # Nếu chưa có PK => create => không cần before
    if not getattr(instance, "pk", None):
        return

    try:
        # Lấy bản cũ từ DB
        old = sender._base_manager.filter(pk=instance.pk).first()
        if old is None:
            return
        instance._audit_before = _snapshot_instance(old)  # type: ignore[attr-defined]
    except Exception:
        return


# ==========================================================
# CREATE / UPDATE
# ==========================================================

@receiver(post_save)
def _audit_post_save(sender, instance, created: bool, raw: bool = False, using=None, update_fields=None, **kwargs):
    # raw=True khi loaddata/fixture -> bỏ qua
    if raw:
        return
    if _should_skip(sender, instance):
        return

    try:
        tenant = get_current_tenant()
    except Exception:
        tenant = None

    # AFTER snapshot
    after = _snapshot_instance(instance)

    # BEFORE snapshot (nếu update)
    before = getattr(instance, "_audit_before", None)
    if before is None:
        before = {}

    action = AuditLog.ACTION_CREATE if created else AuditLog.ACTION_UPDATE

    diff_map, changed_fields = _diff(before, after) if not created else ({}, [])

    # Meta: để trống, hoặc bạn có thể đính update_fields
    meta: Dict[str, Any] = {}
    if update_fields:
        meta["update_fields"] = list(update_fields)

    # Actor + request meta: bạn đang lấy từ “meta context” đâu đó (threadlocal/contextvar)
    # Nếu hiện tại code bạn có hàm get_audit_meta() thì gắn vào đây.
    # Ở đây mình để mặc định None/"" để không nổ.
    actor = getattr(instance, "_audit_actor", None)  # optional nếu bạn tự set từ middleware
    path = getattr(instance, "_audit_path", "") or ""
    method = getattr(instance, "_audit_method", "") or ""
    ip_address = getattr(instance, "_audit_ip", None)
    user_agent = getattr(instance, "_audit_user_agent", None)
    referer = getattr(instance, "_audit_referer", None)

    # Lưu audit
    AuditLog.objects.create(
        tenant=tenant,
        actor=actor,
        action=action,
        app_label=sender._meta.app_label,
        model_name=sender._meta.model_name,
        object_pk=str(getattr(instance, "pk", "")),
        path=str(path),
        method=str(method),
        ip_address=ip_address,
        user_agent=user_agent,
        referer=referer,
        before=_to_jsonable(before),
        after=_to_jsonable(after),
        changed_fields=_to_jsonable(changed_fields),
        meta=_to_jsonable(meta),
    )


# ==========================================================
# DELETE
# ==========================================================

@receiver(post_delete)
def _audit_post_delete(sender, instance, using=None, **kwargs):
    if _should_skip(sender, instance):
        return

    try:
        tenant = get_current_tenant()
    except Exception:
        tenant = None

    before = _snapshot_instance(instance)

    actor = getattr(instance, "_audit_actor", None)
    path = getattr(instance, "_audit_path", "") or ""
    method = getattr(instance, "_audit_method", "") or ""
    ip_address = getattr(instance, "_audit_ip", None)
    user_agent = getattr(instance, "_audit_user_agent", None)
    referer = getattr(instance, "_audit_referer", None)

    AuditLog.objects.create(
        tenant=tenant,
        actor=actor,
        action=AuditLog.ACTION_DELETE,
        app_label=sender._meta.app_label,
        model_name=sender._meta.model_name,
        object_pk=str(getattr(instance, "pk", "")),
        path=str(path),
        method=str(method),
        ip_address=ip_address,
        user_agent=user_agent,
        referer=referer,
        before=_to_jsonable(before),
        after=None,
        changed_fields=[],
        meta={},
    )