# apps/os/timeline_engine.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from django.db.models import Q
from django.utils import timezone

from apps.events.models import OutboxEvent
from apps.work.models import WorkItem, WorkComment, WorkItemTransitionLog


# =========================
# Cursor (keyset pagination)
# =========================
@dataclass(frozen=True)
class TimelineCursor:
    before_ts: Optional[str] = None  # ISO8601
    before_id: Optional[int] = None


def _iso(dt) -> str:
    if not dt:
        return ""
    try:
        return dt.isoformat()
    except Exception:
        return str(dt)


def _parse_int(v, default=None):
    try:
        if v is None or v == "":
            return default
        return int(v)
    except Exception:
        return default


def _parse_hours(v, default=24, min_v=1, max_v=24 * 30) -> int:
    h = _parse_int(v, default)
    if h is None:
        return default
    return max(min_v, min(max_v, h))


def _parse_limit(v, default=50, min_v=1, max_v=200) -> int:
    n = _parse_int(v, default)
    if n is None:
        return default
    return max(min_v, min(max_v, n))


def _parse_cursor(cursor: Optional[TimelineCursor]) -> TimelineCursor:
    """
    Normalize cursor:
    - before_ts: isoformat, aware nếu naive
    - before_id: int
    """
    if not cursor:
        return TimelineCursor()

    before_ts = (cursor.before_ts or "").strip() or None
    before_id = _parse_int(cursor.before_id, None)

    if before_ts:
        try:
            dt = datetime.fromisoformat(before_ts)
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            before_ts = dt.isoformat()
        except Exception:
            before_ts = None

    return TimelineCursor(before_ts=before_ts, before_id=before_id)


def _apply_cursor_q(*, dt_field: str, id_field: str, cursor: TimelineCursor) -> Q:
    """
    Keyset:
      (dt < before_ts) OR (dt = before_ts AND id < before_id)
    """
    if not cursor.before_ts:
        return Q()

    try:
        before_dt = datetime.fromisoformat(cursor.before_ts)
        if timezone.is_naive(before_dt):
            before_dt = timezone.make_aware(before_dt, timezone.get_current_timezone())
    except Exception:
        return Q()

    q = Q(**{f"{dt_field}__lt": before_dt})
    if cursor.before_id:
        q |= Q(**{dt_field: before_dt, f"{id_field}__lt": int(cursor.before_id)})
    return q


# =========================
# Scope filter builder
# =========================
def _scope_args(
    *,
    tenant_id: int,
    scope: str,
    shop_id: Optional[int],
    company_id: Optional[int],
    project_id: Optional[int],
    actor_id: Optional[int],
) -> Dict[str, Any]:
    """
    Scope:
      - tenant (default)
      - shop
      - company
      - project
      - user (actor)
    """
    scope = (scope or "tenant").strip().lower()

    data: Dict[str, Any] = {"tenant_id": int(tenant_id)}
    if scope == "shop" and shop_id:
        data["shop_id"] = int(shop_id)
    elif scope == "company" and company_id:
        data["company_id"] = int(company_id)
    elif scope == "project" and project_id:
        data["project_id"] = int(project_id)
    elif scope == "user" and actor_id:
        data["actor_id"] = int(actor_id)

    data["_scope"] = scope
    return data


# =========================
# Title mapping (VN)
# =========================
def _tieu_de_su_kien(name: str) -> str:
    n = (name or "").strip()
    if n == "work.item.created":
        return "Tạo công việc"
    if n == "work.item.updated":
        return "Cập nhật công việc"
    return "Sự kiện hệ thống"


def _tieu_de_workitem(wi: WorkItem) -> str:
    return "Công việc mới"


def _tieu_de_comment() -> str:
    return "Bình luận"


def _tieu_de_transition() -> str:
    return "Chuyển trạng thái"


# =========================
# Main builder
# =========================
def build_os_timeline(
    *,
    tenant_id: int,
    scope: str = "tenant",
    hours: int = 24,
    limit: int = 50,
    cursor: Optional[TimelineCursor] = None,
    shop_id: Optional[int] = None,
    company_id: Optional[int] = None,
    project_id: Optional[int] = None,
    actor_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Output chuẩn:
      {
        "items": [...],
        "next_cursor": {"before_ts": "...", "before_id": ...} | None
      }
    """
    cursor = _parse_cursor(cursor)
    hours = _parse_hours(hours, default=24)
    limit = _parse_limit(limit, default=50)

    now = timezone.now()
    since = now - timezone.timedelta(hours=int(hours))

    base = _scope_args(
        tenant_id=tenant_id,
        scope=scope,
        shop_id=shop_id,
        company_id=company_id,
        project_id=project_id,
        actor_id=actor_id,
    )
    sc = base.get("_scope", "tenant")

    # Để merge sort mượt, mỗi nguồn lấy dư 1 chút (không quá to)
    fetch_n = min(300, max(80, int(limit) * 2))

    # =========================
    # 1) OUTBOX EVENTS
    # =========================
    ev_q = Q(tenant_id=base["tenant_id"]) & Q(created_at__gte=since)
    if base.get("shop_id"):
        ev_q &= Q(shop_id=base["shop_id"])
    if base.get("company_id"):
        ev_q &= Q(company_id=base["company_id"])
    # project scope: OutboxEvent chưa có project_id -> bỏ qua
    if base.get("actor_id"):
        ev_q &= Q(actor_id=base["actor_id"])

    ev_q &= _apply_cursor_q(dt_field="created_at", id_field="id", cursor=cursor)

    events = list(
        OutboxEvent.objects_all.filter(ev_q)
        .only(
            "id",
            "tenant_id",
            "company_id",
            "shop_id",
            "actor_id",
            "name",
            "payload",
            "created_at",
            "status",
        )
        .order_by("-created_at", "-id")[:fetch_n]
    )

    # =========================
    # 2) WORK ITEMS
    # =========================
    wi_q = Q(tenant_id=base["tenant_id"]) & Q(created_at__gte=since)
    if base.get("shop_id"):
        wi_q &= Q(shop_id=base["shop_id"])
    if base.get("company_id"):
        wi_q &= Q(company_id=base["company_id"])
    if base.get("project_id"):
        wi_q &= Q(project_id=base["project_id"])
    if base.get("actor_id") and sc == "user":
        wi_q &= Q(Q(created_by_id=base["actor_id"]) | Q(assignee_id=base["actor_id"]) | Q(requester_id=base["actor_id"]))

    wi_q &= _apply_cursor_q(dt_field="created_at", id_field="id", cursor=cursor)

    work_items = list(
        WorkItem.objects_all.filter(wi_q)
        .only(
            "id",
            "tenant_id",
            "company_id",
            "project_id",
            "shop_id",
            "title",
            "status",
            "priority",
            "created_at",
            "created_by_id",
            "assignee_id",
            "requester_id",
        )
        .order_by("-created_at", "-id")[:fetch_n]
    )

    # =========================
    # 3) COMMENTS
    # =========================
    wc_q = Q(tenant_id=base["tenant_id"]) & Q(created_at__gte=since)
    if base.get("shop_id"):
        wc_q &= Q(work_item__shop_id=base["shop_id"])
    if base.get("company_id"):
        wc_q &= Q(work_item__company_id=base["company_id"])
    if base.get("project_id"):
        wc_q &= Q(work_item__project_id=base["project_id"])
    if base.get("actor_id"):
        wc_q &= Q(actor_id=base["actor_id"])

    wc_q &= _apply_cursor_q(dt_field="created_at", id_field="id", cursor=cursor)

    comments = list(
        WorkComment.objects_all.select_related("work_item")
        .filter(wc_q)
        .only(
            "id",
            "tenant_id",
            "work_item_id",
            "actor_id",
            "body",
            "created_at",
            "work_item__company_id",
            "work_item__shop_id",
            "work_item__project_id",
        )
        .order_by("-created_at", "-id")[:fetch_n]
    )

    # =========================
    # 4) TRANSITIONS
    # =========================
    tl_q = Q(tenant_id=base["tenant_id"]) & Q(created_at__gte=since)
    if base.get("company_id"):
        tl_q &= Q(company_id=base["company_id"])
    if base.get("project_id"):
        tl_q &= Q(project_id=base["project_id"])
    if base.get("actor_id"):
        tl_q &= Q(actor_id=base["actor_id"])
    # shop scope: join qua workitem
    if base.get("shop_id"):
        tl_q &= Q(workitem__shop_id=base["shop_id"])

    tl_q &= _apply_cursor_q(dt_field="created_at", id_field="id", cursor=cursor)

    transitions = list(
        WorkItemTransitionLog.objects_all.select_related("workitem")
        .filter(tl_q)
        .only(
            "id",
            "tenant_id",
            "company_id",
            "project_id",
            "workitem_id",
            "from_status",
            "to_status",
            "actor_id",
            "reason",
            "created_at",
            "workitem__shop_id",
        )
        .order_by("-created_at", "-id")[:fetch_n]
    )

    # =========================
    # Normalize (VN keys)
    # =========================
    items: List[Dict[str, Any]] = []

    for ev in events:
        payload = ev.payload or {}
        items.append(
            {
                "id": f"event:{ev.id}",
                "loai": "su_kien",
                "tieu_de": _tieu_de_su_kien(ev.name),
                "noi_dung": (ev.name or "").strip(),
                "trang_thai": (ev.status or "").strip(),
                "tenant_id": ev.tenant_id,
                "company_id": ev.company_id,
                "shop_id": ev.shop_id,
                "project_id": None,
                "actor_id": ev.actor_id,
                "doi_tuong": {"loai": "outbox_event", "id": ev.id},
                "payload": payload,
                "thoi_gian": _iso(ev.created_at),
                "_sort_dt": ev.created_at,
                "_sort_id": int(ev.id),
            }
        )

    for wi in work_items:
        items.append(
            {
                "id": f"workitem:{wi.id}",
                "loai": "cong_viec",
                "tieu_de": _tieu_de_workitem(wi),
                "noi_dung": (wi.title or "").strip(),
                "trang_thai": (wi.status or "").strip(),
                "tenant_id": wi.tenant_id,
                "company_id": wi.company_id,
                "shop_id": getattr(wi, "shop_id", None),
                "project_id": wi.project_id,
                "actor_id": getattr(wi, "created_by_id", None),
                "doi_tuong": {"loai": "workitem", "id": wi.id},
                "payload": {
                    "priority": int(wi.priority or 0),
                    "assignee_id": getattr(wi, "assignee_id", None),
                    "requester_id": getattr(wi, "requester_id", None),
                },
                "thoi_gian": _iso(wi.created_at),
                "_sort_dt": wi.created_at,
                "_sort_id": int(wi.id),
            }
        )

    for c in comments:
        wi = getattr(c, "work_item", None)
        items.append(
            {
                "id": f"comment:{c.id}",
                "loai": "binh_luan",
                "tieu_de": _tieu_de_comment(),
                "noi_dung": (c.body or "").strip(),
                "trang_thai": "",
                "tenant_id": c.tenant_id,
                "company_id": getattr(wi, "company_id", None),
                "shop_id": getattr(wi, "shop_id", None),
                "project_id": getattr(wi, "project_id", None),
                "actor_id": getattr(c, "actor_id", None),
                "doi_tuong": {"loai": "workitem", "id": c.work_item_id},
                "payload": {},
                "thoi_gian": _iso(c.created_at),
                "_sort_dt": c.created_at,
                "_sort_id": int(c.id),
            }
        )

    for t in transitions:
        w = getattr(t, "workitem", None)
        items.append(
            {
                "id": f"transition:{t.id}",
                "loai": "chuyen_trang_thai",
                "tieu_de": _tieu_de_transition(),
                "noi_dung": f"{(t.from_status or '').strip()} → {(t.to_status or '').strip()}".strip(),
                "trang_thai": (t.to_status or "").strip(),
                "tenant_id": t.tenant_id,
                "company_id": t.company_id,
                "shop_id": getattr(w, "shop_id", None),
                "project_id": t.project_id,
                "actor_id": getattr(t, "actor_id", None),
                "doi_tuong": {"loai": "workitem", "id": t.workitem_id},
                "payload": {"ly_do": (t.reason or "").strip()},
                "thoi_gian": _iso(t.created_at),
                "_sort_dt": t.created_at,
                "_sort_id": int(t.id),
            }
        )

    # =========================
    # Merge-sort + cut + cursor
    # =========================
    items.sort(key=lambda x: (x["_sort_dt"], x["_sort_id"]), reverse=True)
    items = items[:limit]

    next_cursor = None
    if items:
        last = items[-1]
        last_dt = last.get("_sort_dt")
        last_id = last.get("_sort_id")
        if last_dt and last_id:
            next_cursor = {"before_ts": _iso(last_dt), "before_id": int(last_id)}

    # cleanup internal keys
    for it in items:
        it.pop("_sort_dt", None)
        it.pop("_sort_id", None)

    return {"items": items, "next_cursor": next_cursor}