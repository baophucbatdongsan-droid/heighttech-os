# apps/intelligence/escalation.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone

from apps.intelligence.models import ShopActionItem
from apps.intelligence.notifier import send_webhook


# =========================================================
# Status sets
# =========================================================

OPEN_STATUSES = {
    getattr(ShopActionItem, "STATUS_OPEN", "open"),
    getattr(ShopActionItem, "STATUS_DOING", "doing"),
    getattr(ShopActionItem, "STATUS_BLOCKED", "blocked"),
}

CLOSED_STATUSES = {
    getattr(ShopActionItem, "STATUS_DONE", "done"),
    getattr(ShopActionItem, "STATUS_VERIFIED", "verified"),
}


# =========================================================
# Helpers
# =========================================================

def _now() -> datetime:
    return timezone.now()


def _parse_sev(x: str) -> str:
    x = (x or "P2").upper().strip()
    if x not in ("P0", "P1", "P2"):
        return "P2"
    return x


def _rank_map() -> Dict[str, int]:
    # rank nhỏ hơn = nặng hơn
    return {"P0": 0, "P1": 1, "P2": 2}


def _sev_rank_expr():
    """
    Rank nhỏ hơn => nặng hơn.
    P0=0, P1=1, P2=2
    """
    return Case(
        When(severity="P0", then=Value(0)),
        When(severity="P1", then=Value(1)),
        When(severity="P2", then=Value(2)),
        default=Value(9),
        output_field=IntegerField(),
    )


def _bump_severity(cur: str, target: str) -> str:
    """Chỉ bump lên (nặng hơn), không hạ."""
    cur = _parse_sev(cur)
    target = _parse_sev(target)
    rank = _rank_map()
    # nếu target nặng hơn cur => rank[target] < rank[cur]
    return target if rank[target] < rank[cur] else cur


def _safe_append_note(old: str, line: str) -> str:
    old = old or ""
    line = (line or "").strip()
    if not line:
        return old
    if line in old:
        return old
    return f"{old}\n{line}" if old else line


def _jsonsafe(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k): _jsonsafe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonsafe(x) for x in v]
    return v


def _due_by_severity(sev: str, now: datetime) -> Optional[datetime]:
    sev = _parse_sev(sev)
    if sev == "P0":
        return now + timedelta(hours=24)
    if sev == "P1":
        return now + timedelta(hours=72)
    return now + timedelta(days=7)


def _age_days(obj: ShopActionItem, now: datetime) -> Optional[float]:
    """
    Tuổi ticket theo updated_at nếu có, fallback created_at.
    """
    ts = getattr(obj, "updated_at", None) or getattr(obj, "created_at", None)
    if not ts:
        return None
    return (now - ts).total_seconds() / 86400.0


# =========================================================
# Result DTO
# =========================================================

@dataclass
class EscalationResult:
    dry_run: bool
    month: str
    scanned: int
    updated: int
    forced_p0: int
    bumps: int
    unassigned: int
    reassigned: int
    notified_p0: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "month": self.month,
            "scanned": self.scanned,
            "updated": self.updated,
            "forced_p0": self.forced_p0,
            "bumps": self.bumps,
            "unassigned": self.unassigned,
            "reassigned": self.reassigned,
            "notified_p0": self.notified_p0,
        }


# =========================================================
# Rules
# =========================================================

def _should_bump_by_overdue(obj: ShopActionItem, now: datetime) -> Optional[str]:
    """
    Overdue rule:
    - overdue >= 1 ngày: P2 -> P1
    - overdue >= 3 ngày: P1/P2 -> P0
    - overdue >= 7 ngày: force P0
    """
    due_at = getattr(obj, "due_at", None)
    if not due_at or due_at > now:
        return None

    days_over = (now - due_at).total_seconds() / 86400.0
    cur = _parse_sev(getattr(obj, "severity", "P2"))

    if days_over >= 7:
        return "P0"
    if days_over >= 3 and cur in ("P1", "P2"):
        return "P0"
    if days_over >= 1 and cur == "P2":
        return "P1"
    return None


def _should_force_p0_by_blocked(obj: ShopActionItem, now: datetime, lookback_days: int) -> bool:
    """
    BLOCKED lâu (dựa updated_at/created_at) => force P0
    """
    status = (getattr(obj, "status", "") or "").strip()
    if status != getattr(ShopActionItem, "STATUS_BLOCKED", "blocked"):
        return False

    ts = getattr(obj, "updated_at", None) or getattr(obj, "created_at", None)
    if not ts:
        return False

    return ts <= now - timedelta(days=max(1, int(lookback_days)))


def _should_bump_by_stale(
    obj: ShopActionItem,
    now: datetime,
    *,
    stale_p2_to_p1_days: int,
    stale_p1_to_p0_days: int,
    stale_p0_force_days: int,
) -> Optional[str]:
    """
    CẤP 10: Stale rule theo tuổi ticket (updated_at/created_at)
    - P2 stale >= stale_p2_to_p1_days => P1
    - P1 stale >= stale_p1_to_p0_days => P0
    - P0 stale >= stale_p0_force_days => P0 (thực chất vẫn P0, nhưng có thể ghi note nếu muốn)
    """
    age = _age_days(obj, now)
    if age is None:
        return None

    cur = _parse_sev(getattr(obj, "severity", "P2"))

    if cur == "P2" and age >= max(1, int(stale_p2_to_p1_days)):
        return "P1"
    if cur == "P1" and age >= max(1, int(stale_p1_to_p0_days)):
        return "P0"
    if cur == "P0" and age >= max(1, int(stale_p0_force_days)):
        return "P0"
    return None


def _autofill_due_at(
    *,
    objs: Sequence[ShopActionItem],
    dry_run: bool,
    now: datetime,
    changes: Optional[List[Dict[str, Any]]],
) -> int:
    """
    Nếu OPEN mà chưa có due_at => set theo severity.
    """
    if changes is None:
        changes = []

    cnt = 0
    for obj in objs:
        if (getattr(obj, "status", "") or "").strip() not in OPEN_STATUSES:
            continue
        if getattr(obj, "due_at", None):
            continue

        due = _due_by_severity(getattr(obj, "severity", "P2"), now)
        if not due:
            continue

        if not dry_run:
            obj.due_at = due
            obj.note = _safe_append_note(obj.note, f"[AUTO] Set due_at theo severity lúc {now:%Y-%m-%d %H:%M}")
            obj.save(update_fields=["due_at", "note", "updated_at"])

        changes.append({
            "type": "AUTO_DUE",
            "id": obj.id,
            "shop_id": obj.shop_id,
            "shop_name": obj.shop_name,
            "title": obj.title,
            "severity": getattr(obj, "severity", ""),
            "reason": f"Auto set due_at ({_parse_sev(getattr(obj, 'severity', 'P2'))})",
        })
        cnt += 1

    return cnt


def _owner_overload_unassign(
    *,
    qs,
    owner_p0_limit: int,
    owner_p1p0_limit: int,
    dry_run: bool,
    changes: Optional[List[Dict[str, Any]]],
) -> int:
    """
    Owner overload:
    - owner có quá nhiều P0 open => unassign bớt
    - owner có quá nhiều (P0+P1) open => unassign bớt
    """
    if not hasattr(ShopActionItem, "owner"):
        return 0
    if changes is None:
        changes = []

    owner_p0_limit = max(0, int(owner_p0_limit))
    owner_p1p0_limit = max(0, int(owner_p1p0_limit))
    if owner_p0_limit == 0 and owner_p1p0_limit == 0:
        return 0

    now = _now()
    unassigned = 0

    owners = (
        qs.exclude(owner_id__isnull=True)
        .values_list("owner_id", flat=True)
        .distinct()
    )

    for oid in owners:
        owner_qs = qs.filter(owner_id=oid)

        # ----- Limit P0 -----
        if owner_p0_limit > 0:
            p0 = owner_qs.filter(severity="P0")
            cnt = p0.count()
            if cnt > owner_p0_limit:
                extra = cnt - owner_p0_limit

                # giữ cái due gần / có due, còn lại unassign
                victims = (
                    p0.order_by(
                        Case(
                            When(due_at__isnull=True, then=Value(1)),
                            default=Value(0),
                            output_field=IntegerField(),
                        ),
                        "due_at",
                        "-id",
                    )
                )[owner_p0_limit: owner_p0_limit + extra]

                if not dry_run:
                    for v in victims:
                        v.owner_id = None
                        v.note = _safe_append_note(v.note, f"[AUTO] Unassign do quá tải P0 lúc {now:%Y-%m-%d %H:%M}")
                        v.save(update_fields=["owner", "note", "updated_at"])

                for v in victims:
                    changes.append({
                        "type": "UNASSIGN",
                        "id": v.id,
                        "shop_id": v.shop_id,
                        "shop_name": v.shop_name,
                        "title": v.title,
                        "severity": v.severity,
                        "old_owner": oid,
                        "new_owner": None,
                        "reason": f"Owner {oid} quá tải P0: {cnt}>{owner_p0_limit}",
                    })

                unassigned += victims.count()

        # ----- Limit P0+P1 -----
        if owner_p1p0_limit > 0:
            p1p0 = owner_qs.filter(severity__in=["P0", "P1"])
            cnt = p1p0.count()
            if cnt > owner_p1p0_limit:
                extra = cnt - owner_p1p0_limit

                victims = (
                    p1p0.annotate(_sev_rank=_sev_rank_expr())
                    .order_by("_sev_rank", "due_at", "-id")
                )[owner_p1p0_limit: owner_p1p0_limit + extra]

                if not dry_run:
                    for v in victims:
                        v.owner_id = None
                        v.note = _safe_append_note(v.note, f"[AUTO] Unassign do quá tải P1/P0 lúc {now:%Y-%m-%d %H:%M}")
                        v.save(update_fields=["owner", "note", "updated_at"])

                for v in victims:
                    changes.append({
                        "type": "UNASSIGN",
                        "id": v.id,
                        "shop_id": v.shop_id,
                        "shop_name": v.shop_name,
                        "title": v.title,
                        "severity": v.severity,
                        "old_owner": oid,
                        "new_owner": None,
                        "reason": f"Owner {oid} quá tải P1/P0: {cnt}>{owner_p1p0_limit}",
                    })

                unassigned += victims.count()

    return unassigned


def _auto_assign_least_loaded(
    *,
    month: Optional[date],
    owner_pool: List[int],
    cooldown_minutes: int,
    allow_overload: bool,
    owner_p0_limit: int,
    owner_p1p0_limit: int,
    dry_run: bool,
    changes: Optional[List[Dict[str, Any]]],
) -> int:
    """
    Auto-assign ticket OPEN chưa có owner theo least-loaded.
    - cooldown_minutes: skip ticket vừa update gần đây (tránh reassign liên tục)
    - allow_overload: vẫn assign dù pool vượt limit (pool nhỏ)
    """
    if not owner_pool:
        return 0
    if not hasattr(ShopActionItem, "owner_id"):
        return 0
    if changes is None:
        changes = []

    now = _now()
    cooldown_minutes = max(0, int(cooldown_minutes))
    allow_overload = bool(allow_overload)

    qs = ShopActionItem.objects.filter(status__in=list(OPEN_STATUSES), owner_id__isnull=True)
    if month:
        qs = qs.filter(month=month)

    if cooldown_minutes > 0 and hasattr(ShopActionItem, "updated_at"):
        qs = qs.filter(updated_at__lte=now - timedelta(minutes=cooldown_minutes))

    tickets = list(qs.annotate(_sev_rank=_sev_rank_expr()).order_by("_sev_rank", "due_at", "-id"))
    if not tickets:
        return 0

    pool = []
    seen = set()
    for x in owner_pool:
        try:
            ix = int(x)
        except Exception:
            continue
        if ix not in seen:
            seen.add(ix)
            pool.append(ix)

    if not pool:
        return 0

    open_qs = ShopActionItem.objects.filter(status__in=list(OPEN_STATUSES), owner_id__in=pool)
    if month:
        open_qs = open_qs.filter(month=month)

    counts_p0: Dict[int, int] = {oid: open_qs.filter(owner_id=oid, severity="P0").count() for oid in pool}
    counts_p1p0: Dict[int, int] = {oid: open_qs.filter(owner_id=oid, severity__in=["P0", "P1"]).count() for oid in pool}

    def pick_owner(sev: str) -> Optional[int]:
        sev = _parse_sev(sev)
        candidates: List[tuple] = []

        for oid in pool:
            p0 = counts_p0.get(oid, 0)
            p1p0 = counts_p1p0.get(oid, 0)

            if not allow_overload:
                if sev == "P0" and owner_p0_limit > 0 and p0 >= owner_p0_limit:
                    continue
                if sev in ("P0", "P1") and owner_p1p0_limit > 0 and p1p0 >= owner_p1p0_limit:
                    continue

            candidates.append((oid, p0, p1p0))

        if not candidates and allow_overload:
            candidates = [(oid, counts_p0.get(oid, 0), counts_p1p0.get(oid, 0)) for oid in pool]

        if not candidates:
            return None

        # least-loaded: ưu tiên p0 rồi p1p0
        candidates.sort(key=lambda x: (x[1], x[2], x[0]))
        return candidates[0][0]

    reassigned = 0

    for t in tickets:
        oid = pick_owner(getattr(t, "severity", "P2"))
        if not oid:
            continue

        if not dry_run:
            t.owner_id = oid
            t.note = _safe_append_note(t.note, f"[AUTO] Auto-assign least-loaded (pool={pool}) lúc {now:%Y-%m-%d %H:%M}")
            t.save(update_fields=["owner", "note", "updated_at"])

        sev = _parse_sev(getattr(t, "severity", "P2"))
        if sev == "P0":
            counts_p0[oid] = counts_p0.get(oid, 0) + 1
            counts_p1p0[oid] = counts_p1p0.get(oid, 0) + 1
        elif sev == "P1":
            counts_p1p0[oid] = counts_p1p0.get(oid, 0) + 1

        changes.append({
            "type": "ASSIGN",
            "id": t.id,
            "shop_id": t.shop_id,
            "shop_name": t.shop_name,
            "title": t.title,
            "severity": t.severity,
            "old_owner": None,
            "new_owner": oid,
            "reason": f"Auto-assign least-loaded (pool={pool})",
        })
        reassigned += 1

    return reassigned


# =========================================================
# Public API (FINAL - matches command)
# =========================================================

def run_escalation_engine(
    *,
    month: Optional[date] = None,
    lookback_days: int = 21,
    owner_p0_limit: int = 3,
    owner_p1p0_limit: int = 10,
    dry_run: bool = True,
    notify: bool = False,
    max_scan: int = 5000,

    # CẤP 10
    autodue: bool = True,
    stale_p2_to_p1_days: int = 7,
    stale_p1_to_p0_days: int = 14,
    stale_p0_force_days: int = 21,

    owner_pool: Optional[List[int]] = None,
    cooldown_minutes: int = 120,
    allow_overload: bool = False,

    # collector from command
    changes: Optional[List[Dict[str, Any]]] = None,
) -> EscalationResult:
    """
    FINAL:
    - Trả EscalationResult (object)
    - Nếu truyền `changes` list thì engine append change logs vào đó
    """
    now = _now()
    lookback_days = max(1, int(lookback_days))
    max_scan = max(1, int(max_scan))

    if changes is None:
        changes = []

    qs = ShopActionItem.objects.filter(status__in=list(OPEN_STATUSES))
    if month:
        qs = qs.filter(month=month)

    since = now - timedelta(days=lookback_days)
    if hasattr(ShopActionItem, "updated_at"):
        qs = qs.filter(updated_at__gte=since)
    elif hasattr(ShopActionItem, "created_at"):
        qs = qs.filter(created_at__gte=since)

    objs: List[ShopActionItem] = list(
        qs.annotate(_sev_rank=_sev_rank_expr()).order_by("_sev_rank", "-id")[:max_scan]
    )

    scanned = len(objs)
    updated = 0
    forced_p0 = 0
    bumps = 0
    notified_p0 = 0

    new_p0_payloads: List[Dict[str, Any]] = []

    def _apply_change(obj: ShopActionItem, new_sev: str, reason: str):
        nonlocal updated, forced_p0, bumps, new_p0_payloads

        cur = _parse_sev(getattr(obj, "severity", "P2"))
        new_sev = _parse_sev(new_sev)

        if cur == new_sev:
            return

        # bump only (nặng hơn)
        rank = _rank_map()
        if rank[new_sev] > rank[cur]:
            return

        obj.severity = new_sev
        obj.note = _safe_append_note(obj.note, reason)

        if not dry_run:
            obj.save(update_fields=["severity", "note", "updated_at"])

        updated += 1

        if new_sev == "P0" and cur != "P0":
            forced_p0 += 1
            changes.append({
                "type": "FORCE_P0",
                "id": obj.id,
                "shop_id": obj.shop_id,
                "shop_name": obj.shop_name,
                "title": obj.title,
                "from": cur,
                "to": new_sev,
                "reason": reason,
            })
            new_p0_payloads.append({
                "id": obj.id,
                "shop_id": obj.shop_id,
                "shop_name": obj.shop_name,
                "company_name": obj.company_name,
                "title": obj.title,
                "status": obj.status,
                "source": getattr(obj, "source", ""),
                "due_at": _jsonsafe(getattr(obj, "due_at", None)),
                "reason": reason,
            })
        else:
            bumps += 1
            changes.append({
                "type": "BUMP",
                "id": obj.id,
                "shop_id": obj.shop_id,
                "shop_name": obj.shop_name,
                "title": obj.title,
                "from": cur,
                "to": new_sev,
                "reason": reason,
            })

    # 1) autodue trước
    if autodue:
        _autofill_due_at(objs=objs, dry_run=dry_run, now=now, changes=changes)

    # 2) apply escalation rules
    for obj in objs:
        # overdue
        target = _should_bump_by_overdue(obj, now)
        if target:
            bumped = _bump_severity(getattr(obj, "severity", "P2"), target)
            if bumped != _parse_sev(getattr(obj, "severity", "P2")):
                _apply_change(obj, bumped, f"[AUTO] Overdue => bump {target} lúc {now:%Y-%m-%d %H:%M}")

        # blocked 오래
        if _should_force_p0_by_blocked(obj, now, lookback_days=lookback_days):
            _apply_change(obj, "P0", f"[AUTO] BLOCKED quá {lookback_days} ngày => force P0 lúc {now:%Y-%m-%d %H:%M}")

        # stale rules
        target2 = _should_bump_by_stale(
            obj,
            now,
            stale_p2_to_p1_days=stale_p2_to_p1_days,
            stale_p1_to_p0_days=stale_p1_to_p0_days,
            stale_p0_force_days=stale_p0_force_days,
        )
        if target2:
            bumped2 = _bump_severity(getattr(obj, "severity", "P2"), target2)
            if bumped2 != _parse_sev(getattr(obj, "severity", "P2")):
                _apply_change(obj, bumped2, f"[AUTO] Stale => bump {target2} lúc {now:%Y-%m-%d %H:%M}")

    # 3) owner overload -> unassign
    base_open_qs = ShopActionItem.objects.filter(status__in=list(OPEN_STATUSES))
    if month:
        base_open_qs = base_open_qs.filter(month=month)

    unassigned = _owner_overload_unassign(
        qs=base_open_qs,
        owner_p0_limit=owner_p0_limit,
        owner_p1p0_limit=owner_p1p0_limit,
        dry_run=dry_run,
        changes=changes,
    )

    # 4) auto-assign pool (sau khi unassign)
    reassigned = 0
    if owner_pool:
        reassigned = _auto_assign_least_loaded(
            month=month,
            owner_pool=owner_pool,
            cooldown_minutes=cooldown_minutes,
            allow_overload=allow_overload,
            owner_p0_limit=owner_p0_limit,
            owner_p1p0_limit=owner_p1p0_limit,
            dry_run=dry_run,
            changes=changes,
        )

    # 5) notify new P0
    if notify and new_p0_payloads:
        try:
            send_webhook(_jsonsafe({
                "type": "ESCALATION_P0",
                "month": month.isoformat() if month else "all",
                "count": len(new_p0_payloads),
                "items": new_p0_payloads[:20],
            }))
            notified_p0 = min(len(new_p0_payloads), 20)
        except Exception:
            notified_p0 = 0

    return EscalationResult(
        dry_run=bool(dry_run),
        month=(month.isoformat() if month else "all"),
        scanned=scanned,
        updated=updated,
        forced_p0=forced_p0,
        bumps=bumps,
        unassigned=unassigned,
        reassigned=reassigned,
        notified_p0=notified_p0,
    )