# apps/work/services_move.py
from __future__ import annotations

import time
from typing import Optional, List, Any, Union

from django.db import IntegrityError, transaction, connection
from django.db.models import Case, When, Value, CharField

from apps.work.models import WorkItem

# =====================================================
# Advisory locks (BACKWARD-COMPAT + stable hashing)
# =====================================================

_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
LockPart = Union[int, str]


def _fnv1a_64(data: bytes) -> int:
    h = 1469598103934665603
    for b in data:
        h ^= b
        h = (h * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h


def _stable_i32(x: Any) -> int:
    """
    Convert arbitrary key to a stable 31-bit positive int.
    - int/bool: use numeric value
    - str/bytes/other: hash -> stable int
    """
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
    """
    PostgreSQL advisory transaction lock.
    Works with mixed types: ints + strings ("todo"/"doing") safely.
    MUST be called inside transaction.atomic().
    """
    if getattr(connection, "vendor", "") != "postgresql":
        return

    # pg_advisory_xact_lock supports:
    #   - (bigint)
    #   - (int, int)
    # We'll use (int, int) stable mixing.
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


def _lock_column(*, tenant_id: int, company_id: int, status: str) -> None:
    """
    Transaction-scoped lock per (tenant, company, status).
    Must be called INSIDE atomic().
    """
    status = (status or "").strip().lower()
    _advisory_xact_lock("workitem.column", tenant_id, company_id, status)


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
    """
    pos_1based: 1..N
    rank string fixed-length so lexical order matches numeric order.
    """
    if pos_1based < 1:
        pos_1based = 1
    s = _base36(pos_1based)
    return s.rjust(width, "0")


def _tmp_rank_for_id(_id: int, width: int = 10) -> str:
    """
    Temporary rank that will NEVER collide with normal ranks.
    Normal ranks always start with "0" (zero-padded).
    We'll use prefix "z" + base36(id) padded to (width-1).
    """
    if _id < 0:
        _id = -_id
    s = _base36(_id).rjust(width - 1, "0")
    return ("z" + s)[:width]


def _rebuild_ranks_for_column(
    *,
    tenant_id: int,
    company_id: int,
    status: str,
    ordered_ids: List[int],
) -> None:
    """
    Update all items in (tenant, company, status) to have ranks 1..N
    according to ordered_ids.

    Avoid transient unique collisions by 2-phase update:
      1) assign temp unique ranks based on id (prefix 'z')
      2) assign final ranks using CASE
    """
    if not ordered_ids:
        return

    status = (status or "").strip().lower()

    # Phase 1: temp ranks
    tmp_whens = [When(id=_id, then=Value(_tmp_rank_for_id(_id))) for _id in ordered_ids]
    WorkItem.objects.filter(
        tenant_id=tenant_id,
        company_id=company_id,
        status=status,
        id__in=ordered_ids,
    ).update(rank=Case(*tmp_whens, output_field=CharField()))

    # Phase 2: final ranks 1..N
    final_whens = [
        When(id=_id, then=Value(_rank_for_pos(idx)))
        for idx, _id in enumerate(ordered_ids, start=1)
    ]
    WorkItem.objects.filter(
        tenant_id=tenant_id,
        company_id=company_id,
        status=status,
        id__in=ordered_ids,
    ).update(rank=Case(*final_whens, output_field=CharField()))


# =====================================================
# Public services
# =====================================================

def create_work_item(
    *,
    tenant_id: int,
    company_id: int,
    title: str,
    status: str = "todo",
    created_by_id: int,
    requester_id: int,
) -> WorkItem:
    """
    Create item and assign rank safely under column lock.
    """
    status = (status or "todo").strip().lower()

    max_retries = 15
    for attempt in range(1, max_retries + 1):
        try:
            with transaction.atomic():
                _lock_column(tenant_id=tenant_id, company_id=company_id, status=status)

                n = WorkItem.objects.filter(
                    tenant_id=tenant_id,
                    company_id=company_id,
                    status=status,
                ).count()

                wi = WorkItem.objects.create(
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
            # Rebuild column then retry
            try:
                with transaction.atomic():
                    _lock_column(tenant_id=tenant_id, company_id=company_id, status=status)
                    ids = list(
                        WorkItem.objects.filter(
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
) -> None:
    """
    Move item to another status/position using rank ordering.

    Guarantees under advisory locks:
    - lock columns in stable order (reduce deadlock risk)
    - rebuild ranks 2-phase to avoid unique collisions
    """
    max_retries = 20

    for attempt in range(1, max_retries + 1):
        try:
            with transaction.atomic():
                base = (
                    WorkItem.objects.only("id", "tenant_id", "company_id", "status")
                    .get(id=item_id, tenant_id=tenant_id)
                )
                company_id = base.company_id
                from_status = (base.status or "").strip().lower()
                target_status = (to_status or from_status).strip().lower()

                pos = 1 if to_position is None else int(to_position)
                if pos < 1:
                    pos = 1

                # lock columns in sorted order
                for st in sorted({from_status, target_status}):
                    _lock_column(tenant_id=tenant_id, company_id=company_id, status=st)

                # lock row
                wi = (
                    WorkItem.objects.select_for_update()
                    .only("id", "tenant_id", "company_id", "status", "rank")
                    .get(id=item_id, tenant_id=tenant_id)
                )

                from_status = (wi.status or "").strip().lower()
                if not target_status:
                    target_status = from_status

                if target_status != from_status:
                    WorkItem.objects.filter(id=wi.id).update(status=target_status)
                    wi.status = target_status

                ids = list(
                    WorkItem.objects.filter(
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
                return

        except WorkItem.DoesNotExist:
            return

        except IntegrityError as e:
            if attempt == max_retries:
                raise IntegrityError("move_work_item failed after retries (integrity persists)") from e
            time.sleep(0.01 * attempt)

    raise IntegrityError("move_work_item failed after retries")


# =====================================================
# Backward-compat helpers (keep old imports alive)
# =====================================================

def _rank_to_int(rank: str) -> int:
    r = (rank or "").strip().lower()
    if not r:
        return 0
    n = 0
    for ch in r:
        # if dirty ranks exist with prefix 'z', keep them parseable by treating 'z' as 35
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
    company_id: int,
    status: str,
) -> None:
    status = (status or "").strip().lower()
    if not status:
        return

    with transaction.atomic():
        _lock_column(tenant_id=tenant_id, company_id=company_id, status=status)
        ids = list(
            WorkItem.objects.filter(
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