# apps/intelligence/ops_metrics.py
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from django.db.models import Q
from django.utils import timezone

from apps.intelligence.models import ShopActionItem


def _now() -> datetime:
    return timezone.now()


def _open_statuses() -> List[str]:
    return [
        getattr(ShopActionItem, "STATUS_OPEN", "open"),
        getattr(ShopActionItem, "STATUS_DOING", "doing"),
        getattr(ShopActionItem, "STATUS_BLOCKED", "blocked"),
    ]


def _closed_statuses() -> List[str]:
    return [
        getattr(ShopActionItem, "STATUS_DONE", "done"),
        getattr(ShopActionItem, "STATUS_VERIFIED", "verified"),
    ]


def _has_field(field_name: str) -> bool:
    try:
        ShopActionItem._meta.get_field(field_name)
        return True
    except Exception:
        return False


HAS_OWNER = _has_field("owner")
HAS_DUE_AT = _has_field("due_at")
HAS_UPDATED_AT = _has_field("updated_at")
HAS_CREATED_AT = _has_field("created_at")


def build_ops_queryset(
    *,
    month=None,
    only_open: bool = True,
):
    qs = ShopActionItem.objects.all()
    if only_open:
        qs = qs.filter(status__in=_open_statuses())
    if month:
        qs = qs.filter(month=month)
    return qs


def calc_ops_health(
    *,
    month=None,
    blocked_days: int = 21,
) -> Dict[str, Any]:
    """
    Founder Ops Health snapshot:
    - totals open
    - P0/P1/P2
    - overdue (due_at < now)
    - blocked lâu (status=blocked & updated_at/created_at <= now - blocked_days)
    - unassigned (owner is null) if has owner
    - owner load breakdown (P0, P0+P1, open total)
    """
    now = _now()
    blocked_days = max(1, int(blocked_days))

    qs = build_ops_queryset(month=month, only_open=True)

    total_open = qs.count()
    p0 = qs.filter(severity="P0").count()
    p1 = qs.filter(severity="P1").count()
    p2 = qs.filter(severity="P2").count()

    # overdue
    overdue = 0
    if HAS_DUE_AT:
        overdue = qs.filter(due_at__isnull=False, due_at__lt=now).count()

    # blocked long
    blocked_long = 0
    blocked_status = getattr(ShopActionItem, "STATUS_BLOCKED", "blocked")
    if HAS_UPDATED_AT:
        blocked_long = qs.filter(
            status=blocked_status,
            updated_at__lte=now - timedelta(days=blocked_days),
        ).count()
    elif HAS_CREATED_AT:
        blocked_long = qs.filter(
            status=blocked_status,
            created_at__lte=now - timedelta(days=blocked_days),
        ).count()

    # unassigned
    unassigned = 0
    if HAS_OWNER:
        unassigned = qs.filter(owner_id__isnull=True).count()

    # owner breakdown
    owners_breakdown: List[Dict[str, Any]] = []
    if HAS_OWNER:
        owner_ids = list(
            qs.exclude(owner_id__isnull=True).values_list("owner_id", flat=True).distinct()
        )

        for oid in owner_ids:
            oqs = qs.filter(owner_id=oid)
            owners_breakdown.append({
                "owner_id": oid,
                "open_total": oqs.count(),
                "p0_open": oqs.filter(severity="P0").count(),
                "p1p0_open": oqs.filter(severity__in=["P0", "P1"]).count(),
                "overdue": (oqs.filter(due_at__isnull=False, due_at__lt=now).count() if HAS_DUE_AT else 0),
            })

        # sort: nhiều P0 trước, rồi P0+P1, rồi overdue
        owners_breakdown.sort(key=lambda x: (-x["p0_open"], -x["p1p0_open"], -x["overdue"], x["owner_id"]))

    return {
        "month": (month.isoformat() if month else "all"),
        "generated_at": now.isoformat(),
        "totals": {
            "open": total_open,
            "p0": p0,
            "p1": p1,
            "p2": p2,
            "overdue": overdue,
            "blocked_long": blocked_long,
            "unassigned": unassigned,
        },
        "owners": owners_breakdown,
        "params": {
            "blocked_days": blocked_days,
        },
    }


def calc_owner_performance(
    *,
    month=None,
    days: int = 30,
    owner_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Owner performance:
    - open load (P0, P0+P1, total open)
    - closed in last N days (done/verified)
    - overdue open
    """
    now = _now()
    days = max(1, int(days))
    since = now - timedelta(days=days)

    open_qs = build_ops_queryset(month=month, only_open=True)
    closed_qs = ShopActionItem.objects.all().filter(status__in=_closed_statuses())
    if month:
        closed_qs = closed_qs.filter(month=month)

    # filter closed time window
    if _has_field("closed_at"):
        closed_qs = closed_qs.filter(closed_at__isnull=False, closed_at__gte=since)
    elif HAS_UPDATED_AT:
        closed_qs = closed_qs.filter(updated_at__gte=since)
    elif HAS_CREATED_AT:
        closed_qs = closed_qs.filter(created_at__gte=since)

    if not HAS_OWNER:
        # không có owner thì trả rỗng
        return {
            "month": (month.isoformat() if month else "all"),
            "generated_at": now.isoformat(),
            "days": days,
            "items": [],
        }

    # pick owners
    if owner_ids:
        owner_ids = [int(x) for x in owner_ids if str(x).strip().isdigit()]
    else:
        owner_ids = list(
            open_qs.exclude(owner_id__isnull=True).values_list("owner_id", flat=True).distinct()
        )
        # cũng lấy cả owner chỉ có closed
        owner_ids2 = list(
            closed_qs.exclude(owner_id__isnull=True).values_list("owner_id", flat=True).distinct()
        )
        owner_ids = sorted(set(owner_ids + owner_ids2))

    items: List[Dict[str, Any]] = []
    for oid in owner_ids:
        oqs = open_qs.filter(owner_id=oid)
        cqs = closed_qs.filter(owner_id=oid)

        overdue_open = 0
        if HAS_DUE_AT:
            overdue_open = oqs.filter(due_at__isnull=False, due_at__lt=now).count()

        items.append({
            "owner_id": oid,
            "open_total": oqs.count(),
            "p0_open": oqs.filter(severity="P0").count(),
            "p1p0_open": oqs.filter(severity__in=["P0", "P1"]).count(),
            "overdue_open": overdue_open,
            "closed_last_days": cqs.count(),
        })

    # leaderboard: ít P0, ít overdue, đóng nhiều => top
    def score(x: Dict[str, Any]) -> int:
        # bạn tune thoải mái
        return int(x["closed_last_days"] * 10 - x["p0_open"] * 8 - x["overdue_open"] * 5 - x["p1p0_open"] * 2)

    for it in items:
        it["score"] = score(it)

    items.sort(key=lambda x: (-x["score"], x["owner_id"]))

    return {
        "month": (month.isoformat() if month else "all"),
        "generated_at": now.isoformat(),
        "days": days,
        "items": items,
    }