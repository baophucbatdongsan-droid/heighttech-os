# apps/notifications/service.py
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from django.db import IntegrityError
from django.utils import timezone

from apps.notifications.models import Notification

logger = logging.getLogger(__name__)


def tao_thong_bao(
    *,
    tenant_id: int,
    company_id: Optional[int],
    shop_id: Optional[int],
    actor_id: Optional[int],
    user_id: Optional[int],
    level: str,
    tieu_de: str,
    noi_dung: str,
    doi_tuong_loai: str = "",
    doi_tuong_id: Optional[int] = None,
    dedupe_key: str = "",
    meta: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    lvl = (level or "info").strip().lower()
    if lvl not in {
        Notification.Level.INFO,
        Notification.Level.WARNING,
        Notification.Level.CRITICAL,
    }:
        lvl = Notification.Level.INFO

    data = dict(
        tenant_id=int(tenant_id),
        company_id=int(company_id) if company_id else None,
        shop_id=int(shop_id) if shop_id else None,
        actor_id=int(actor_id) if actor_id else None,
        user_id=int(user_id) if user_id else None,
        level=lvl,
        status=Notification.Status.UNREAD,
        tieu_de=(tieu_de or "").strip(),
        noi_dung=(noi_dung or "").strip(),
        doi_tuong_loai=(doi_tuong_loai or "").strip(),
        doi_tuong_id=int(doi_tuong_id) if doi_tuong_id else None,
        dedupe_key=(dedupe_key or "").strip(),
        meta=meta or {},
        created_at=timezone.now(),
    )

    try:
        obj = Notification.objects_all.create(**data)
        return int(obj.id)
    except IntegrityError:
        # duplicate dedupe_key => ignore
        return None
    except Exception:
        logger.exception(
            "tao_thong_bao failed tenant_id=%s title=%s",
            tenant_id,
            (tieu_de or "").strip(),
        )
        return None