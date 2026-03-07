# apps/intelligence/action_engine_legacy.py
from __future__ import annotations

from typing import Any, Dict, Optional

from django.utils import timezone

from apps.events.models import OutboxEvent
from apps.work.models import WorkItem


def _ensure_task(
    *,
    tenant_id: int,
    company_id: Optional[int],
    shop_id: Optional[int],
    title: str,
    description: str = "",
    priority: int = 2,
    type: str = "task",
    visible_to_client: bool = False,
    is_internal: bool = True,
) -> Optional[int]:
    title = (title or "").strip()
    if not title:
        return None

    since = timezone.now() - timezone.timedelta(hours=24)
    qs = WorkItem.objects_all.filter(
        tenant_id=int(tenant_id),
        shop_id=shop_id,
        title=title,
        created_at__gte=since,
    )
    if qs.exists():
        return int(qs.order_by("-id").first().id)

    obj = WorkItem(
        tenant_id=int(tenant_id),
        company_id=company_id,
        shop_id=shop_id,
        title=title,
        description=description,
        priority=int(priority or 2),
        type=type,
        visible_to_client=bool(visible_to_client),
        is_internal=bool(is_internal),
        status=WorkItem.Status.TODO,
        position=1,
    )
    obj.save()
    return int(obj.id)


def on_work_item_updated(ev: OutboxEvent) -> None:
    p: Dict[str, Any] = ev.payload or {}

    tenant_id = int(ev.tenant_id)  # ✅ FK int
    company_id = getattr(ev, "company_id_id", None) or ev.company_id
    shop_id = getattr(ev, "shop_id_id", None) or ev.shop_id

    status = (p.get("status") or "").strip().lower()
    priority = int(p.get("priority") or 0)
    assignee_id = p.get("assignee_id")

    if priority >= 4 and not assignee_id:
        _ensure_task(
            tenant_id=tenant_id,
            company_id=company_id,
            shop_id=shop_id,
            title="(TỰ ĐỘNG) Gán người phụ trách cho task KHẨN",
            description=f"Task khẩn nhưng chưa có người phụ trách. WorkItem #{p.get('id')}",
            priority=3,
            type="task",
            is_internal=True,
            visible_to_client=False,
        )

    if status == "blocked":
        _ensure_task(
            tenant_id=tenant_id,
            company_id=company_id,
            shop_id=shop_id,
            title="(TỰ ĐỘNG) Gỡ trạng thái BLOCKED trong 24h",
            description=f"Task đang bị chặn. WorkItem #{p.get('id')}",
            priority=3,
            type="task",
            is_internal=True,
            visible_to_client=False,
        )