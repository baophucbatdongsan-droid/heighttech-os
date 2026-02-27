# apps/work/services_move.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.db.models import F, Max

from apps.work.models import WorkItem


@dataclass
class MoveResult:
    item: WorkItem
    from_status: str
    to_status: str
    from_position: int
    to_position: int


def _clamp_pos(pos: int, max_pos: int) -> int:
    if pos < 1:
        return 1
    if max_pos < 1:
        return 1
    if pos > max_pos:
        return max_pos
    return pos


@transaction.atomic
def move_work_item(
    *,
    tenant_id: int,
    item_id: int,
    to_status: str,
    to_position: Optional[int] = None,
) -> MoveResult:
    """
    Reorder WorkItem theo position trong "cột" (company_id + status).
    - Nếu đổi status => remove khỏi cột cũ, insert vào cột mới.
    - Nếu cùng status => reorder trong cột đó.
    """

    # lock item
    item = (
        WorkItem.objects_all.select_for_update()
        .select_related("company")
        .get(id=item_id, tenant_id=tenant_id)
    )

    from_status = item.status
    from_position = int(item.position or 1)

    # validate status
    valid_statuses = {s for s, _ in WorkItem.Status.choices}
    if to_status not in valid_statuses:
        raise ValueError(f"Invalid to_status: {to_status}")

    # key scope: tenant + company + status
    # (Nếu sau này bạn muốn scope theo project nữa thì thêm project_id vào filter)
    base_old = WorkItem.objects_all.select_for_update().filter(
        tenant_id=tenant_id,
        company_id=item.company_id,
        status=from_status,
    )

    base_new = WorkItem.objects_all.select_for_update().filter(
        tenant_id=tenant_id,
        company_id=item.company_id,
        status=to_status,
    )

    # Nếu to_position không truyền -> thả xuống cuối cột mới
    if to_position is None:
        max_pos = base_new.aggregate(m=Max("position"))["m"] or 0
        to_position = int(max_pos) + 1
    else:
        to_position = int(to_position)

    if from_status == to_status:
        # ===== REORDER SAME COLUMN =====
        # max_pos trong cột hiện tại
        max_pos = base_old.exclude(id=item.id).aggregate(m=Max("position"))["m"] or 0
        # nếu move trong cùng cột, max_pos + 1 (vì item đang tồn tại)
        max_pos = int(max_pos) + 1
        to_position = _clamp_pos(to_position, max_pos)

        if to_position == from_position:
            return MoveResult(
                item=item,
                from_status=from_status,
                to_status=to_status,
                from_position=from_position,
                to_position=to_position,
            )

        if to_position < from_position:
            # kéo lên: các item [to_pos .. from_pos-1] +1
            base_old.exclude(id=item.id).filter(
                position__gte=to_position,
                position__lt=from_position,
            ).update(position=F("position") + 1)
        else:
            # kéo xuống: các item [from_pos+1 .. to_pos] -1
            base_old.exclude(id=item.id).filter(
                position__gt=from_position,
                position__lte=to_position,
            ).update(position=F("position") - 1)

        WorkItem.objects_all.filter(id=item.id).update(position=to_position)
        item.position = to_position

        return MoveResult(
            item=item,
            from_status=from_status,
            to_status=to_status,
            from_position=from_position,
            to_position=to_position,
        )

    # ===== MOVE TO ANOTHER COLUMN =====
    # 1) remove khỏi cột cũ: các item > from_pos bị kéo lên (-1)
    base_old.exclude(id=item.id).filter(position__gt=from_position).update(
        position=F("position") - 1
    )

    # 2) insert vào cột mới: clamp theo size cột mới + 1
    max_pos_new = base_new.aggregate(m=Max("position"))["m"] or 0
    max_pos_new = int(max_pos_new) + 1
    to_position = _clamp_pos(to_position, max_pos_new)

    # các item >= to_pos bị đẩy xuống (+1)
    base_new.filter(position__gte=to_position).update(position=F("position") + 1)

    # 3) update item
    WorkItem.objects_all.filter(id=item.id).update(status=to_status, position=to_position)
    item.status = to_status
    item.position = to_position

    return MoveResult(
        item=item,
        from_status=from_status,
        to_status=to_status,
        from_position=from_position,
        to_position=to_position,
    )