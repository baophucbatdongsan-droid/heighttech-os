# apps/os/notifications_service.py
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
        return None

    obj = OSNotification.objects_all.create(
        tenant_id=int(tenant_id),
        target_role=(target_role or "").strip().lower(),
        target_user_id=target_user_id,
        severity=(severity or "info").strip().lower(),
        status=(status or "new").strip().lower(),
        tieu_de=(tieu_de or "Thông báo").strip(),
        noi_dung=(noi_dung or "").strip(),
        entity_kind=(entity_kind or "").strip(),
        entity_id=entity_id,
        company_id=company_id,
        shop_id=shop_id,
        actor_id=actor_id,
        meta=meta or {},
        created_at=timezone.now(),
    )
    return obj