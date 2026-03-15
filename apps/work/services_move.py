# apps/work/services_move.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, List, Any, Union

from django.db import IntegrityError, transaction, connection
from django.db.models import Case, When, Value, CharField

from apps.work.models import WorkItem
from apps.os.notifications_service import create_notification

# =====================================================
# Advisory locks (BACKWARD-COMPAT + stable hashing)
# =====================================================

_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
LockPart = Union[int, str]


@dataclass
class MoveResult:
    from_status: str
    to_status: str
    from_position: int
    to_position: int


def _fnv1a_64(data: bytes) -> int:
    h = 1469598103934665603
    for b in data:
        h ^= b
        h = (h * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h


def _stable_i32(x: Any) -> int:
    if isinstance(x, bool):
        v = 1 if x else 0
    elif isinstance(x, int):
        v = x
    elif isinstance(x, bytes):
        v = _fnv1a_64(x)
    elif isinstance(x, str):
        v = _fnv1a_64(x.encode("utf-8"))
    else:
        v = _fnv1a_64(repr(x).encode("utf-8"))

    v = int(v) & 0xFFFFFFFF
    return v & 0x7FFFFFFF


def _advisory_xact_lock(*keys: Any) -> None:
    if getattr(connection, "vendor", "") != "postgresql":
        return

    k1 = 0
    k2 = 0
    for i, k in enumerate(keys):
        h = _stable_i32(k)
        if i % 2 == 0:
            k1 = (k1 * 1315423911 + h) & 0x7FFFFFFF
        else:
            k2 = (k2 * 2654435761 + h) & 0x7FFFFFFF

    with connection.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s, %s)", [k1, k2])


def _company_lock_key(company_id: Optional[int]) -> int:
    return int(company_id or 0)


def _lock_column(*, tenant_id: int, company_id: Optional[int], status: str) -> None:
    status = (status or "").strip().lower()
    _advisory_xact_lock("workitem.column", tenant_id, _company_lock_key(company_id), status)


# =====================================================
# Rank helpers (fixed-length base36)
# =====================================================

def _base36(n: int) -> str:
    if n < 0:
        raise ValueError("n must be >= 0")
    if n == 0:
        return "0"
    out: List[str] = []
    while n:
        n, r = divmod(n, 36)
        out.append(_ALPHABET[r])
    return "".join(reversed(out))


def _rank_for_pos(pos_1based: int, width: int = 10) -> str:
    if pos_1based < 1:
        pos_1based = 1
    s = _base36(pos_1based)
    return s.rjust(width, "0")


def _tmp_rank_for_id(_id: int, width: int = 10) -> str:
    if _id < 0:
        _id = -_id
    s = _base36(_id).rjust(width - 1, "0")
    return ("z" + s)[:width]


def _column_qs(*, tenant_id: int, company_id: Optional[int], status: str):
    qs = WorkItem.objects_all.filter(
        tenant_id=tenant_id,
        status=(status or "").strip().lower(),
    )
    if company_id is None:
        return qs.filter(company_id__isnull=True)
    return qs.filter(company_id=company_id)


def _rebuild_ranks_for_column(
    *,
    tenant_id: int,
    company_id: Optional[int],
    status: str,
    ordered_ids: List[int],
) -> None:
    if not ordered_ids:
        return

    status = (status or "").strip().lower()
    qs = _column_qs(
        tenant_id=tenant_id,
        company_id=company_id,
        status=status,
    ).filter(id__in=ordered_ids)

    tmp_whens = [When(id=_id, then=Value(_tmp_rank_for_id(_id))) for _id in ordered_ids]
    qs.update(rank=Case(*tmp_whens, output_field=CharField()))

    final_whens = [
        When(id=_id, then=Value(_rank_for_pos(idx)))
        for idx, _id in enumerate(ordered_ids, start=1)
    ]
    qs.update(rank=Case(*final_whens, output_field=CharField()))


def _position_in_ids(ids: List[int], item_id: int) -> int:
    try:
        return ids.index(item_id) + 1
    except ValueError:
        return 0


# =====================================================
# Public services
# =====================================================

def create_work_item(
    *,
    tenant_id: int,
    company_id: Optional[int],
    title: str,
    status: str = "todo",
    created_by_id: int,
    requester_id: int,
) -> WorkItem:
    status = (status or "todo").strip().lower()

    max_retries = 15
    for attempt in range(1, max_retries + 1):
        try:
            with transaction.atomic():
                _lock_column(tenant_id=tenant_id, company_id=company_id, status=status)

                n = _column_qs(
                    tenant_id=tenant_id,
                    company_id=company_id,
                    status=status,
                ).count()

                wi = WorkItem.objects_all.create(
                    tenant_id=tenant_id,
                    company_id=company_id,
                    title=title,
                    status=status,
                    rank=_rank_for_pos(n + 1),
                    created_by_id=created_by_id,
                    requester_id=requester_id,
                )
                return wi

        except IntegrityError:
            if attempt == max_retries:
                raise
            try:
                with transaction.atomic():
                    _lock_column(tenant_id=tenant_id, company_id=company_id, status=status)
                    ids = list(
                        _column_qs(
                            tenant_id=tenant_id,
                            company_id=company_id,
                            status=status,
                        )
                        .order_by("rank", "id")
                        .values_list("id", flat=True)
                    )
                    _rebuild_ranks_for_column(
                        tenant_id=tenant_id,
                        company_id=company_id,
                        status=status,
                        ordered_ids=ids,
                    )
            except Exception:
                pass
            time.sleep(0.01 * attempt)

    raise IntegrityError("create_work_item failed after retries")


def move_work_item(
    *,
    tenant_id: int,
    item_id: int,
    to_status: Optional[str] = None,
    to_position: Optional[int] = None,
    actor_id: Optional[int] = None,
) -> MoveResult:
    max_retries = 20

    for attempt in range(1, max_retries + 1):
        try:
            with transaction.atomic():
                base = (
                    WorkItem.objects_all.only(
                        "id",
                        "tenant_id",
                        "company_id",
                        "shop_id",
                        "status",
                        "rank",
                        "title",
                    )
                    .get(id=item_id, tenant_id=tenant_id)
                )

                company_id = base.company_id
                from_status = (base.status or "").strip().lower()
                target_status = (to_status or from_status).strip().lower()
                if not target_status:
                    target_status = from_status

                current_ids = list(
                    _column_qs(
                        tenant_id=tenant_id,
                        company_id=company_id,
                        status=from_status,
                    )
                    .order_by("rank", "id")
                    .values_list("id", flat=True)
                )
                from_position = _position_in_ids(current_ids, item_id)

                pos = 1 if to_position is None else int(to_position)
                if pos < 1:
                    pos = 1

                for st in sorted({from_status, target_status}):
                    _lock_column(
                        tenant_id=tenant_id,
                        company_id=company_id,
                        status=st,
                    )

                wi = (
                    WorkItem.objects_all.select_for_update()
                    .only(
                        "id",
                        "tenant_id",
                        "company_id",
                        "shop_id",
                        "status",
                        "rank",
                        "title",
                        "updated_at",
                    )
                    .get(id=item_id, tenant_id=tenant_id)
                )

                from_status = (wi.status or "").strip().lower()
                if not target_status:
                    target_status = from_status

                if target_status != from_status:
                    tmp_rank = _tmp_rank_for_id(wi.id)

                    WorkItem.objects_all.filter(
                        id=wi.id,
                        tenant_id=tenant_id,
                    ).update(
                        rank=tmp_rank,
                        status=target_status,
                    )

                    wi.refresh_from_db(fields=["id", "tenant_id", "company_id", "shop_id", "status", "rank", "title"])

                ids = list(
                    _column_qs(
                        tenant_id=tenant_id,
                        company_id=company_id,
                        status=target_status,
                    )
                    .exclude(id=wi.id)
                    .order_by("rank", "id")
                    .values_list("id", flat=True)
                )

                insert_idx = min(max(pos - 1, 0), len(ids))
                ids.insert(insert_idx, wi.id)

                _rebuild_ranks_for_column(
                    tenant_id=tenant_id,
                    company_id=company_id,
                    status=target_status,
                    ordered_ids=ids,
                )

                if from_status != target_status:
                    old_ids = list(
                        _column_qs(
                            tenant_id=tenant_id,
                            company_id=company_id,
                            status=from_status,
                        )
                        .order_by("rank", "id")
                        .values_list("id", flat=True)
                    )

                    _rebuild_ranks_for_column(
                        tenant_id=tenant_id,
                        company_id=company_id,
                        status=from_status,
                        ordered_ids=old_ids,
                    )

                result = MoveResult(
                    from_status=from_status,
                    to_status=target_status,
                    from_position=from_position if from_position > 0 else 1,
                    to_position=insert_idx + 1,
                )

                wi.refresh_from_db(fields=["id", "tenant_id", "company_id", "shop_id", "status", "rank", "title"])

            try:
                changed_column = result.from_status != result.to_status
                changed_position = result.from_position != result.to_position

                if changed_column or changed_position:
                    create_notification(
                        tenant_id=int(tenant_id),
                        tieu_de="Task đã thay đổi",
                        noi_dung=(
                            f"{(wi.title or f'Task #{wi.id}')} • "
                            f"{result.from_status} → {result.to_status} • "
                            f"vị trí {result.from_position} → {result.to_position}"
                        ),
                        severity="info",
                        status="new",
                        entity_kind="work_item",
                        entity_id=wi.id,
                        company_id=wi.company_id,
                        shop_id=getattr(wi, "shop_id", None),
                        actor_id=actor_id,
                        meta={
                            "source": "work_move",
                            "task_id": wi.id,
                            "title": wi.title,
                            "from_status": result.from_status,
                            "to_status": result.to_status,
                            "from_position": result.from_position,
                            "to_position": result.to_position,
                        },
                    )
            except Exception as e:
                print("create_notification error:", e)

            return result

        except WorkItem.DoesNotExist:
            raise ValueError(f"WorkItem {item_id} không tồn tại trong tenant {tenant_id}")

        except IntegrityError as e:
            if attempt == max_retries:
                raise IntegrityError("move_work_item failed after retries (integrity persists)") from e
            time.sleep(0.01 * attempt)

    raise IntegrityError("move_work_item failed after retries")


# =====================================================
# Backward-compat helpers
# =====================================================

def _rank_to_int(rank: str) -> int:
    r = (rank or "").strip().lower()
    if not r:
        return 0
    n = 0
    for ch in r:
        if ch not in _ALPHABET:
            raise ValueError(f"invalid rank char: {ch!r}")
        n = n * 36 + _ALPHABET.index(ch)
    return n


def _int_to_rank(n: int, width: int = 10) -> str:
    if n < 0:
        n = 0
    s = _base36(n)
    return s.rjust(width, "0")


def _pick_rank_between(
    left: Optional[str],
    right: Optional[str],
    *,
    width: int = 10,
) -> str:
    lo = _rank_to_int(left) if left else 0
    hi = _rank_to_int(right) if right else (36 ** width) - 1
    if hi <= lo:
        raise ValueError("invalid bounds: right must be > left")
    mid = (lo + hi) // 2
    if mid == lo:
        raise ValueError("no space between ranks; need rebuild")
    return _int_to_rank(mid, width=width)


def _rebalance_column(
    *,
    tenant_id: int,
    company_id: Optional[int],
    status: str,
) -> None:
    status = (status or "").strip().lower()
    if not status:
        return

    with transaction.atomic():
        _lock_column(tenant_id=tenant_id, company_id=company_id, status=status)
        ids = list(
            _column_qs(
                tenant_id=tenant_id,
                company_id=company_id,
                status=status,
            )
            .order_by("rank", "id")
            .values_list("id", flat=True)
        )
        _rebuild_ranks_for_column(
            tenant_id=tenant_id,
            company_id=company_id,
            status=status,
            ordered_ids=ids,
        )