# apps/intelligence/management/commands/escalate_actions.py
from __future__ import annotations

from dataclasses import is_dataclass
from datetime import date
from typing import Any, Dict, List, Optional

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_date

from apps.intelligence.escalation import run_escalation_engine


def _parse_owner_pool(raw: str) -> List[int]:
    raw = (raw or "").strip()
    if not raw:
        return []
    out: List[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except Exception:
            continue
    # unique preserve order
    seen = set()
    uniq: List[int] = []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def _safe_get(res: Any, key: str, default: Any = None) -> Any:
    """
    Hỗ trợ res là:
    - dataclass (EscalationResult)
    - dict
    """
    if res is None:
        return default
    if isinstance(res, dict):
        return res.get(key, default)
    if is_dataclass(res):
        return getattr(res, key, default)
    return getattr(res, key, default)


def _format_change_line(idx: int, c: Dict[str, Any]) -> str:
    t = (c.get("type") or "").upper()
    _id = c.get("id")
    shop_id = c.get("shop_id")
    shop_name = c.get("shop_name") or ""
    title = c.get("title") or ""
    sev = c.get("severity") or ""
    reason = c.get("reason") or ""

    old_owner = c.get("old_owner")
    new_owner = c.get("new_owner")
    sev_from = c.get("from")
    sev_to = c.get("to")

    if t == "UNASSIGN":
        return (
            f"{idx:02d}. [UNASSIGN] id={_id} shop={shop_id} '{shop_name}' | "
            f"owner {old_owner} -> {new_owner} | sev={sev} | title='{title}' | reason={reason}"
        )
    if t == "ASSIGN":
        return (
            f"{idx:02d}. [ASSIGN]   id={_id} shop={shop_id} '{shop_name}' | "
            f"owner {old_owner} -> {new_owner} | sev={sev} | title='{title}' | reason={reason}"
        )
    if t == "AUTO_DUE":
        return (
            f"{idx:02d}. [AUTO_DUE] id={_id} shop={shop_id} '{shop_name}' | "
            f"sev={sev} | title='{title}' | reason={reason}"
        )
    if t in ("BUMP", "FORCE_P0"):
        return (
            f"{idx:02d}. [{t}] id={_id} shop={shop_id} '{shop_name}' | "
            f"sev {sev_from}->{sev_to} | title='{title}' | reason={reason}"
        )
    if t == "NOTE":
        return (
            f"{idx:02d}. [NOTE]     id={_id} shop={shop_id} '{shop_name}' | "
            f"sev={sev} | title='{title}' | reason={reason}"
        )

    # fallback
    return f"{idx:02d}. [{t or 'CHANGE'}] {c}"


class Command(BaseCommand):
    help = "Escalate ShopActionItem tickets (Cấp 10): overdue/stale/block + owner overload + auto-assign pool + auto due SLA"

    def add_arguments(self, parser):
        parser.add_argument("--month", type=str, default="", help="YYYY-MM-01. Bỏ trống = all")
        parser.add_argument("--commit", action="store_true", help="Ghi DB. Không có flag này = DRY RUN")
        parser.add_argument("--notify", action="store_true", help="Gửi webhook khi có P0 mới (nếu engine hỗ trợ)")

        parser.add_argument("--lookback-days", type=int, default=21)
        parser.add_argument("--owner-p0-limit", type=int, default=3)
        parser.add_argument("--owner-p1p0-limit", type=int, default=10)
        parser.add_argument("--max-scan", type=int, default=5000)

        # ✅ CẤP 10: Auto assign
        parser.add_argument("--owner-pool", type=str, default="", help="Danh sách user_id pool, vd: 1,2,3")
        parser.add_argument("--allow-overload", action="store_true", help="Cho phép assign kể cả khi pool quá tải")
        parser.add_argument("--cooldown-minutes", type=int, default=120, help="Không reassign nếu vừa update trong X phút")

        # ✅ CẤP 10: Auto due SLA + stale rules
        parser.add_argument("--no-autodue", action="store_true", help="Tắt auto set due_at nếu ticket thiếu")
        parser.add_argument("--stale-p2-to-p1-days", type=int, default=7)
        parser.add_argument("--stale-p1-to-p0-days", type=int, default=14)
        parser.add_argument("--stale-p0-force-days", type=int, default=21)

        # verbose print
        parser.add_argument("--verbose", action="store_true", help="In chi tiết các thay đổi")
        parser.add_argument("--print-limit", type=int, default=200, help="Giới hạn số dòng in khi --verbose")

    def handle(self, *args, **opts):
        month_str = (opts.get("month") or "").strip()
        commit = bool(opts.get("commit"))
        notify = bool(opts.get("notify"))

        lookback_days = int(opts.get("lookback_days") or 21)
        owner_p0_limit = int(opts.get("owner_p0_limit") or 3)
        owner_p1p0_limit = int(opts.get("owner_p1p0_limit") or 10)
        max_scan = int(opts.get("max_scan") or 5000)

        verbose = bool(opts.get("verbose"))
        print_limit = int(opts.get("print_limit") or 200)

        owner_pool = _parse_owner_pool(opts.get("owner_pool") or "")
        allow_overload = bool(opts.get("allow_overload"))
        cooldown_minutes = int(opts.get("cooldown_minutes") or 120)

        autodue = not bool(opts.get("no_autodue"))

        stale_p2_to_p1_days = int(opts.get("stale_p2_to_p1_days") or 7)
        stale_p1_to_p0_days = int(opts.get("stale_p1_to_p0_days") or 14)
        stale_p0_force_days = int(opts.get("stale_p0_force_days") or 21)

        # month parse
        month: Optional[date] = None
        if month_str:
            d = parse_date(month_str)
            if not d:
                self.stdout.write(self.style.ERROR("month không hợp lệ. Dùng YYYY-MM-DD, ví dụ 2026-02-01"))
                return
            month = d

        # validate owner pool existence (optional - mềm)
        if owner_pool:
            User = get_user_model()
            exists = set(User.objects.filter(id__in=owner_pool).values_list("id", flat=True))
            missing = [x for x in owner_pool if x not in exists]
            if missing:
                self.stdout.write(self.style.WARNING(f"owner_pool có user_id không tồn tại: {missing} (bỏ qua những id này)"))
                owner_pool = [x for x in owner_pool if x in exists]

        changes: List[Dict[str, Any]] = []

        res = run_escalation_engine(
            month=month,
            lookback_days=lookback_days,
            owner_p0_limit=owner_p0_limit,
            owner_p1p0_limit=owner_p1p0_limit,
            dry_run=(not commit),
            notify=notify,
            max_scan=max_scan,

            # ✅ CẤP 10
            autodue=autodue,
            stale_p2_to_p1_days=stale_p2_to_p1_days,
            stale_p1_to_p0_days=stale_p1_to_p0_days,
            stale_p0_force_days=stale_p0_force_days,

            # ✅ auto-assign pool
            owner_pool=owner_pool,
            allow_overload=allow_overload,
            cooldown_minutes=cooldown_minutes,

            # ✅ verbose collector
            changes=changes,
        )

        # summary
        dry_run = bool(_safe_get(res, "dry_run", (not commit)))
        scanned = int(_safe_get(res, "scanned", 0) or 0)
        updated = int(_safe_get(res, "updated", 0) or 0)
        forced_p0 = int(_safe_get(res, "forced_p0", 0) or 0)
        bumps = int(_safe_get(res, "bumps", 0) or 0)
        unassigned = int(_safe_get(res, "unassigned", 0) or 0)
        reassigned = int(_safe_get(res, "reassigned", 0) or 0)  # engine cấp 9/10 có
        notified_p0 = int(_safe_get(res, "notified_p0", 0) or 0)

        self.stdout.write(self.style.SUCCESS(
            f"[Escalation] dry_run={dry_run} month={month_str or 'all'} "
            f"scanned={scanned} updated={updated} forced_p0={forced_p0} bumps={bumps} "
            f"unassigned={unassigned} reassigned={reassigned} notified_p0={notified_p0}"
        ))

        if verbose:
            if not changes:
                self.stdout.write(self.style.WARNING("Không có thay đổi nào để in (--verbose)."))
                return

            self.stdout.write(self.style.WARNING(f"Chi tiết thay đổi (tối đa {print_limit} dòng):"))
            for idx, c in enumerate(changes[:print_limit], start=1):
                self.stdout.write(_format_change_line(idx, c))