from __future__ import annotations

from typing import Any, Dict, Optional

from django.apps import apps
from django.utils import timezone


def _get_model(app_label: str, model_name: str):
    try:
        return apps.get_model(app_label, model_name)
    except Exception:
        return None


def create_notification(
    *,
    tenant_id: int,
    tieu_de: str,
    noi_dung: str,
    severity: str = "info",
    status: str = "new",
    target_role: Optional[str] = None,
    target_user_id: Optional[int] = None,
    entity_kind: Optional[str] = None,
    entity_id: Optional[int] = None,
    company_id: Optional[int] = None,
    shop_id: Optional[int] = None,
    actor_id: Optional[int] = None,
    meta: Optional[Dict[str, Any]] = None,
):
    OSNotification = _get_model("os", "OSNotification")
    if not OSNotification:
        raise RuntimeError("OSNotification model not found")

    sev = (severity or "info").strip().lower()
    if sev not in {"info", "warning", "critical"}:
        sev = "info"

    st = (status or "new").strip().lower()
    if st not in {"new", "read", "archived"}:
        st = "new"

    obj = OSNotification.objects_all.create(
        tenant_id=int(tenant_id),
        company_id=company_id,
        shop_id=shop_id,
        target_user_id=target_user_id,
        target_role=(target_role or "").strip().lower(),
        tieu_de=(tieu_de or "Thông báo").strip(),
        noi_dung=(noi_dung or "").strip(),
        severity=sev,
        entity_kind=(entity_kind or "").strip(),
        entity_id=entity_id,
        meta=meta or {},
        status=st,
        created_at=timezone.now(),
    )
    return obj