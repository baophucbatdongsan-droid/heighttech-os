# scripts/backfill_work_position_v1.py
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Tuple, List

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.work.models import WorkItem

# position sẽ được gán theo thứ tự "cũ -> mới" (để item mới nằm dưới)
# Nếu bạn muốn item mới lên trên thì đảo sort ở dưới.
ORDER_NEWEST_BOTTOM = True

BATCH_SIZE = 500


def _k(wi: WorkItem) -> Tuple[int, int, int, str, int, str]:
    """
    Group key để phân cột Kanban đúng ngữ cảnh:
      tenant + company + project + target_type + target_id + status
    """
    return (
        int(wi.tenant_id or 0),
        int(wi.company_id or 0),
        int(wi.project_id or 0),
        (wi.target_type or "").strip(),
        int(wi.target_id or 0),
        (wi.status or "").strip(),
    )


def run(tenant_id: int | None = None, dry_run: bool = False):
    qs = WorkItem.objects_all.all()

    if tenant_id is not None:
        qs = qs.filter(tenant_id=int(tenant_id))

    # chỉ backfill những record chưa có position hợp lệ (0) hoặc null
    # (field position mình set default=0 nên đa số sẽ là 0)
    qs = qs.filter(position__isnull=False)

    total = qs.count()
    print("==== BACKFILL WORKITEM POSITION v1 ====")
    print("tenant_id:", tenant_id)
    print("total scan:", total)
    print("dry_run:", dry_run)
    print("ORDER_NEWEST_BOTTOM:", ORDER_NEWEST_BOTTOM)

    # Lấy nhẹ: chỉ fields cần
    rows = (
        qs.only(
            "id",
            "tenant_id",
            "company_id",
            "project_id",
            "target_type",
            "target_id",
            "status",
            "position",
            "updated_at",
            "created_at",
        )
        .order_by("tenant_id", "company_id", "project_id", "target_type", "target_id", "status", "id")
    )

    groups: Dict[Tuple[int, int, int, str, int, str], List[int]] = defaultdict(list)
    meta_sort: Dict[int, Tuple] = {}

    for wi in rows.iterator(chunk_size=BATCH_SIZE):
        groups[_k(wi)].append(int(wi.id))

        # Sort key trong mỗi group:
        # - giữ ổn định bằng created_at/updated_at rồi id
        ca = wi.created_at or timezone.now()
        ua = wi.updated_at or ca
        if ORDER_NEWEST_BOTTOM:
            # cũ ở trên, mới ở dưới
            meta_sort[int(wi.id)] = (ua, ca, int(wi.id))
        else:
            # mới ở trên
            meta_sort[int(wi.id)] = (-ua.timestamp(), -ca.timestamp(), -int(wi.id))

    print("groups:", len(groups))

    # Build update map: id -> new_position
    updates: Dict[int, int] = {}
    for gk, ids in groups.items():
        ids_sorted = sorted(ids, key=lambda _id: meta_sort[_id])
        # position bắt đầu từ 1 cho đẹp (0 coi như "unset")
        for idx, _id in enumerate(ids_sorted, start=1):
            updates[_id] = idx

    print("will update items:", len(updates))

    if dry_run:
        # show sample
        sample = list(updates.items())[:20]
        print("sample updates (id -> position):", sample)
        print("DRY RUN done.")
        return

    # Update theo batch (SQLite cũng ổn)
    updated = 0
    ids_all = list(updates.keys())

    with transaction.atomic():
        for i in range(0, len(ids_all), BATCH_SIZE):
            chunk = ids_all[i : i + BATCH_SIZE]
            # Trick: update từng id bằng save sẽ chậm; dùng case/when thì nặng.
            # Cách cân bằng: loop chunk nhỏ.
            for _id in chunk:
                WorkItem.objects_all.filter(id=_id).update(position=updates[_id], updated_at=F("updated_at"))
                updated += 1

    print("UPDATED:", updated)
    print("DONE.")


if __name__ == "__main__":
    # default chạy all tenants
    run()