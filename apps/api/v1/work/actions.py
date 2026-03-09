# apps/api/v1/work/actions.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from django.db import transaction
from django.utils import timezone

from apps.work.models import WorkItem
from apps.work.models_comment import WorkComment


@dataclass
class BulkResult:
    ok: bool
    updated: int
    message: str


def bulk_update_work_items(
    *,
    tenant_id: int,
    actor_id: int | None,
    item_ids: Iterable[int],
    new_status: str | None = None,
    new_assignee_id: int | None = None,
    add_tag: str | None = None,
    remove_tag: str | None = None,
) -> BulkResult:
    ids = [int(x) for x in item_ids if str(x).isdigit()]
    if not ids:
        return BulkResult(ok=False, updated=0, message="Chưa chọn work item nào.")

    if not any([new_status, (new_assignee_id is not None), add_tag, remove_tag]):
        return BulkResult(ok=False, updated=0, message="Không có thay đổi nào để áp dụng.")

    qs = WorkItem.objects_all.filter(tenant_id=tenant_id, id__in=ids)

    with transaction.atomic():
        updated = 0
        now = timezone.now()

        for wi in qs.select_for_update():
            changed = False

            if new_status and wi.status != new_status:
                wi.status = new_status
                changed = True

            if new_assignee_id is not None and wi.assignee_id != new_assignee_id:
                wi.assignee_id = new_assignee_id
                changed = True

            if add_tag:
                tags = list(wi.tags or [])
                if add_tag not in tags:
                    tags.append(add_tag)
                    wi.tags = tags
                    changed = True

            if remove_tag:
                tags = list(wi.tags or [])
                if remove_tag in tags:
                    tags = [t for t in tags if t != remove_tag]
                    wi.tags = tags
                    changed = True

            if changed:
                wi.updated_at = now
                wi.save(update_fields=["status", "assignee", "tags", "updated_at", "started_at", "done_at"])
                updated += 1

                # log comment (nhẹ, sau này tách event log)
                if actor_id:
                    WorkComment.objects_all.create(
                        tenant_id=tenant_id,
                        work_item_id=wi.id,
                        actor_id=actor_id,
                        body="Bulk update",
                        meta={
                            "new_status": new_status,
                            "new_assignee_id": new_assignee_id,
                            "add_tag": add_tag,
                            "remove_tag": remove_tag,
                        },
                    )

    return BulkResult(ok=True, updated=updated, message=f"✅ Bulk update thành công: {updated} item.")