# apps/api/v1/actions.py
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import QuerySet, Q, Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from rest_framework.permissions import IsAuthenticated

from apps.api.v1.base import BaseApi, api_ok, api_error
from apps.api.v1.permissions import AbilityPermission
from apps.core.policy import VIEW_API_FOUNDER
from apps.intelligence.models import ShopActionItem


# =====================================================
# Helpers
# =====================================================
def _jsonify(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, QuerySet):
        return [_jsonify(x) for x in list(obj)]
    if isinstance(obj, dict):
        return {str(k): _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonify(v) for v in obj]
    return obj


def _get_page_params(request, default_size: int = 50, max_size: int = 200) -> Tuple[int, int]:
    try:
        page = int(request.GET.get("page", "1"))
    except Exception:
        page = 1

    try:
        page_size = int(request.GET.get("page_size", str(default_size)))
    except Exception:
        page_size = default_size

    page = max(1, page)
    page_size = max(1, min(page_size, max_size))
    return page, page_size


def _parse_int(x: Any, default: Optional[int] = None) -> Optional[int]:
    if x in (None, "", "null"):
        return default
    try:
        return int(x)
    except Exception:
        return default


def _parse_bool(x: Any, default: Optional[bool] = None) -> Optional[bool]:
    if x is None:
        return default
    if isinstance(x, bool):
        return x
    s = str(x).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    return default


def _parse_dt(x: Any) -> Optional[datetime]:
    """
    Accept:
      - ISO datetime: 2026-02-01T12:00:00Z / +07:00 / naive
      - date: 2026-02-01  (sẽ set 23:59:59)
    """
    if x in (None, "", "null"):
        return None
    if isinstance(x, datetime):
        return x
    if isinstance(x, date):
        return timezone.make_aware(datetime(x.year, x.month, x.day, 23, 59, 59))
    s = str(x).strip()
    dt = parse_datetime(s)
    if dt:
        # nếu dt naive thì make aware theo timezone hiện tại
        if timezone.is_naive(dt):
            return timezone.make_aware(dt)
        return dt
    d = parse_date(s)
    if d:
        dt2 = datetime(d.year, d.month, d.day, 23, 59, 59)
        return timezone.make_aware(dt2)
    return None


def _serialize_action(a: ShopActionItem) -> dict:
    now = timezone.now()
    due_at = getattr(a, "due_at", None)
    closed_at = getattr(a, "closed_at", None)

    overdue = False
    due_in_hours = None
    if due_at and not closed_at:
        overdue = due_at < now
        try:
            due_in_hours = round((due_at - now).total_seconds() / 3600.0, 2)
        except Exception:
            due_in_hours = None

    return {
        "id": a.id,
        "month": a.month.isoformat() if a.month else None,
        "shop_id": a.shop_id,
        "shop_name": a.shop_name or "",
        "company_name": a.company_name or "",

        "title": a.title,
        "severity": a.severity,
        "status": a.status,
        "source": getattr(a, "source", ""),

        "owner_id": getattr(a, "owner_id", None),
        "due_at": due_at.isoformat() if due_at else None,
        "closed_at": closed_at.isoformat() if closed_at else None,

        "verified": bool(getattr(a, "verified", False)),
        "note": a.note or "",
        "payload": a.payload or {},

        # ✅ SLA computed fields
        "overdue": overdue,
        "due_in_hours": due_in_hours,

        "created_at": getattr(a, "created_at", None).isoformat() if getattr(a, "created_at", None) else None,
        "updated_at": getattr(a, "updated_at", None).isoformat() if getattr(a, "updated_at", None) else None,
    }


def _allowed_status_set() -> set:
    return {c[0] for c in getattr(ShopActionItem, "STATUS_CHOICES", [])} or {
        "open", "doing", "blocked", "done", "verified"
    }


def _build_action_q_filter(qs, q: str):
    """
    search chuẩn (không làm mất filter trước)
    """
    if not q:
        return qs
    return qs.filter(
        Q(title__icontains=q) |
        Q(shop_name__icontains=q) |
        Q(company_name__icontains=q)
    )


def _stats_counts(qs) -> Dict[str, Any]:
    """
    counts theo status/severity/source + overdue
    """
    now = timezone.now()
    out: Dict[str, Any] = {
        "total": qs.count(),
        "by_status": {},
        "by_severity": {},
        "by_source": {},
        "overdue": 0,
    }

    # overdue: due_at < now AND closed_at is null (nếu có closed_at)
    if hasattr(ShopActionItem, "due_at"):
        overdue_q = qs.filter(due_at__lt=now)
        if hasattr(ShopActionItem, "closed_at"):
            overdue_q = overdue_q.filter(closed_at__isnull=True)
        out["overdue"] = overdue_q.count()

    for row in qs.values("status").annotate(c=Count("id")):
        out["by_status"][row["status"]] = row["c"]

    for row in qs.values("severity").annotate(c=Count("id")):
        out["by_severity"][row["severity"]] = row["c"]

    if hasattr(ShopActionItem, "source"):
        for row in qs.values("source").annotate(c=Count("id")):
            out["by_source"][row["source"]] = row["c"]

    return out


# =====================================================
# ✅ V1 (GIỮ NGUYÊN - ROUTE CŨ)
# =====================================================
class FounderActionsApi(BaseApi):
    """
    ✅ V1 (đang dùng)
    GET /api/v1/founder/actions/?status=open&severity=P0&source=founder_insight&month=2026-02-01&shop_id=123&q=abc
    """
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_FOUNDER

    def get(self, request):
        qs = ShopActionItem.objects.all()
        if hasattr(ShopActionItem, "owner"):
            qs = qs.select_related("owner")

        status = (request.GET.get("status") or "").strip()
        severity = (request.GET.get("severity") or "").strip()
        source = (request.GET.get("source") or "").strip()
        month = (request.GET.get("month") or "").strip()
        shop_id = (request.GET.get("shop_id") or "").strip()
        q = (request.GET.get("q") or "").strip()

        if status:
            qs = qs.filter(status=status)
        if severity:
            qs = qs.filter(severity=severity)
        if source and hasattr(ShopActionItem, "source"):
            qs = qs.filter(source=source)
        if month:
            d = parse_date(month)
            if d:
                qs = qs.filter(month=d)

        if shop_id:
            try:
                qs = qs.filter(shop_id=int(shop_id))
            except Exception:
                return api_error("bad_shop_id", "shop_id phải là số", status=400)

        if q:
            qs = _build_action_q_filter(qs, q)

        page, page_size = _get_page_params(request, default_size=50, max_size=200)
        paginator = Paginator(qs.order_by("-severity", "-id"), page_size)
        page_obj = paginator.get_page(page)

        items = [_serialize_action(x) for x in page_obj.object_list]
        meta = {
            "page": page_obj.number,
            "page_size": page_size,
            "total_items": paginator.count,
            "total_pages": paginator.num_pages,
            "has_next": page_obj.has_next(),
            "has_prev": page_obj.has_previous(),
        }
        return api_ok({"items": _jsonify(items)}, meta=meta)


class FounderActionUpdateApi(BaseApi):
    """
    ✅ V1 (đang dùng)
    PATCH /api/v1/founder/actions/<id>/
    body json:
      - status
      - owner_id
      - note
      - verified
      - due_at (optional, nếu model có)
    """
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_FOUNDER

    def patch(self, request, action_id: int):
        obj = get_object_or_404(ShopActionItem, pk=action_id)
        data = request.data or {}

        status = data.get("status", None)
        owner_id = data.get("owner_id", None)
        note = data.get("note", None)
        verified = data.get("verified", None)
        due_at = data.get("due_at", None)

        update_fields = []

        if status is not None:
            status = str(status).strip()
            allowed = _allowed_status_set()
            if status not in allowed:
                return api_error("bad_status", f"status không hợp lệ: {status}", status=400)

            obj.status = status
            update_fields.append("status")

            # auto closed_at khi DONE/VERIFIED
            if hasattr(obj, "closed_at"):
                if status in (
                    getattr(ShopActionItem, "STATUS_DONE", "done"),
                    getattr(ShopActionItem, "STATUS_VERIFIED", "verified"),
                ):
                    obj.closed_at = timezone.now()
                else:
                    obj.closed_at = None
                update_fields.append("closed_at")

        if owner_id is not None and hasattr(obj, "owner_id"):
            if owner_id in ("", 0, "0", None):
                obj.owner_id = None
            else:
                try:
                    obj.owner_id = int(owner_id)
                except Exception:
                    return api_error("bad_owner_id", "owner_id phải là số hoặc null", status=400)
            update_fields.append("owner")

        if note is not None:
            obj.note = str(note)
            update_fields.append("note")

        if verified is not None and hasattr(obj, "verified"):
            obj.verified = bool(verified)
            update_fields.append("verified")

        if due_at is not None and hasattr(obj, "due_at"):
            obj.due_at = _parse_dt(due_at)
            update_fields.append("due_at")

        if not update_fields:
            return api_ok(_serialize_action(obj))

        obj.save(update_fields=list(set(update_fields + ["updated_at"])))
        return api_ok(_serialize_action(obj))


# =====================================================
# ✅ V2 (CẤP 4) - ROUTE RIÊNG, KHÔNG ĐÈ V1
# =====================================================
class FounderActionDetailApi(BaseApi):
    """
    ✅ V2 detail
    GET /api/v1/founder/actions/v2/<id>/
    """
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_FOUNDER

    def get(self, request, action_id: int):
        obj = get_object_or_404(ShopActionItem, pk=action_id)
        return api_ok(_serialize_action(obj))


class FounderActionListV2Api(BaseApi):
    """
    ✅ V2 list (cấp 4)
    GET /api/v1/founder/actions/v2/?

    Filters:
      - status=open|doing|blocked|done|verified
      - status_in=open,doing
      - severity=P0|P1|P2
      - source=founder_insight|manual|api|...
      - owner_id=1 | owner_id=null
      - verified=1/0
      - month=YYYY-MM-DD
      - shop_id=123
      - overdue=1 (due_at < now AND chưa closed)
      - due_before=ISO datetime|YYYY-MM-DD
      - due_after=ISO datetime|YYYY-MM-DD
      - q=search

    Sorting:
      - sort=due_at|severity|updated_at|created_at|id
      - order=asc|desc

    Extras:
      - include_stats=1  => trả thêm thống kê tổng
    """
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_FOUNDER

    def get(self, request):
        qs = ShopActionItem.objects.all()
        if hasattr(ShopActionItem, "owner"):
            qs = qs.select_related("owner")

        # params
        status = (request.GET.get("status") or "").strip()
        status_in = (request.GET.get("status_in") or "").strip()
        severity = (request.GET.get("severity") or "").strip()
        source = (request.GET.get("source") or "").strip()

        owner_id_raw = (request.GET.get("owner_id") or "").strip()
        verified_raw = request.GET.get("verified", None)

        month = (request.GET.get("month") or "").strip()
        shop_id = (request.GET.get("shop_id") or "").strip()

        overdue = _parse_bool(request.GET.get("overdue", None), default=None)
        due_before = request.GET.get("due_before", None)
        due_after = request.GET.get("due_after", None)

        q = (request.GET.get("q") or "").strip()

        include_stats = _parse_bool(request.GET.get("include_stats", "0"), default=False)

        sort = (request.GET.get("sort") or "").strip() or "severity"
        order = (request.GET.get("order") or "").strip().lower() or "desc"

        # filters
        if status:
            qs = qs.filter(status=status)

        if status_in:
            parts = [x.strip() for x in status_in.split(",") if x.strip()]
            if parts:
                qs = qs.filter(status__in=parts)

        if severity:
            qs = qs.filter(severity=severity)

        if source and hasattr(ShopActionItem, "source"):
            qs = qs.filter(source=source)

        if owner_id_raw and hasattr(ShopActionItem, "owner_id"):
            if owner_id_raw.lower() in ("null", "none"):
                qs = qs.filter(owner_id__isnull=True)
            else:
                oid = _parse_int(owner_id_raw, default=None)
                if oid is None:
                    return api_error("bad_owner_id", "owner_id phải là số hoặc null", status=400)
                qs = qs.filter(owner_id=oid)

        if verified_raw is not None and hasattr(ShopActionItem, "verified"):
            vb = _parse_bool(verified_raw, default=None)
            if vb is None:
                return api_error("bad_verified", "verified phải là 1/0 hoặc true/false", status=400)
            qs = qs.filter(verified=vb)

        if month:
            d = parse_date(month)
            if d:
                qs = qs.filter(month=d)

        if shop_id:
            try:
                qs = qs.filter(shop_id=int(shop_id))
            except Exception:
                return api_error("bad_shop_id", "shop_id phải là số", status=400)

        if q:
            qs = _build_action_q_filter(qs, q)

        # due range
        if hasattr(ShopActionItem, "due_at"):
            dtb = _parse_dt(due_before)
            dta = _parse_dt(due_after)
            if dtb:
                qs = qs.filter(due_at__lte=dtb)
            if dta:
                qs = qs.filter(due_at__gte=dta)

            if overdue is True:
                now = timezone.now()
                qs = qs.filter(due_at__lt=now)
                if hasattr(ShopActionItem, "closed_at"):
                    qs = qs.filter(closed_at__isnull=True)

        # sort mapping
        sort_map = {
            "due_at": "due_at",
            "severity": "severity",
            "updated_at": "updated_at",
            "created_at": "created_at",
            "id": "id",
        }
        sort_field = sort_map.get(sort, "severity")
        if order == "asc":
            ordering = [sort_field, "-id"]
        else:
            ordering = [f"-{sort_field}", "-id"]

        page, page_size = _get_page_params(request, default_size=50, max_size=200)
        paginator = Paginator(qs.order_by(*ordering), page_size)
        page_obj = paginator.get_page(page)

        items = [_serialize_action(x) for x in page_obj.object_list]

        meta = {
            "page": page_obj.number,
            "page_size": page_size,
            "total_items": paginator.count,
            "total_pages": paginator.num_pages,
            "has_next": page_obj.has_next(),
            "has_prev": page_obj.has_previous(),
        }

        payload: Dict[str, Any] = {"items": _jsonify(items)}
        if include_stats:
            payload["stats"] = _jsonify(_stats_counts(qs))

        return api_ok(payload, meta=meta)


class FounderActionBulkUpdateV2Api(BaseApi):
    """
    ✅ V2 bulk update (cấp 4)
    PATCH /api/v1/founder/actions/v2/bulk/

    body json:
    {
      "ids": [1,2,3],
      "status": "doing",
      "owner_id": 5,           # hoặc null
      "verified": true,
      "note": "ghi chú",       # replace note
      "note_append": "..."     # append note (thêm dòng)
      "due_at": "2026-02-01T12:00:00+07:00"  # hoặc "2026-02-01"
    }
    """
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_FOUNDER

    def patch(self, request):
        data = request.data or {}
        ids = data.get("ids") or []

        if not isinstance(ids, list) or not ids:
            return api_error("bad_ids", "ids phải là list và không được rỗng", status=400)

        ids_int: List[int] = []
        for x in ids:
            v = _parse_int(x, default=None)
            if v is None:
                return api_error("bad_ids", "ids phải là danh sách số", status=400)
            ids_int.append(v)

        status = data.get("status", None)
        owner_id = data.get("owner_id", None)
        verified = data.get("verified", None)
        note = data.get("note", None)
        note_append = data.get("note_append", None)
        due_at = data.get("due_at", None)

        allowed = _allowed_status_set()

        qs = ShopActionItem.objects.filter(id__in=ids_int)

        updated = 0
        with transaction.atomic():
            for obj in qs.select_for_update():
                changed_fields: List[str] = []

                if status is not None:
                    st = str(status).strip()
                    if st not in allowed:
                        return api_error("bad_status", f"status không hợp lệ: {st}", status=400)
                    obj.status = st
                    changed_fields.append("status")

                    if hasattr(obj, "closed_at"):
                        if st in (
                            getattr(ShopActionItem, "STATUS_DONE", "done"),
                            getattr(ShopActionItem, "STATUS_VERIFIED", "verified"),
                        ):
                            obj.closed_at = timezone.now()
                        else:
                            obj.closed_at = None
                        changed_fields.append("closed_at")

                if owner_id is not None and hasattr(obj, "owner_id"):
                    if owner_id in ("", 0, "0", None, "null"):
                        obj.owner_id = None
                    else:
                        oi = _parse_int(owner_id, default=None)
                        if oi is None:
                            return api_error("bad_owner_id", "owner_id phải là số hoặc null", status=400)
                        obj.owner_id = oi
                    changed_fields.append("owner")

                if verified is not None and hasattr(obj, "verified"):
                    obj.verified = bool(_parse_bool(verified, default=False))
                    changed_fields.append("verified")

                if note is not None:
                    obj.note = str(note)
                    changed_fields.append("note")

                if note_append is not None:
                    extra = str(note_append).strip()
                    if extra:
                        if obj.note:
                            obj.note = f"{obj.note}\n{extra}"
                        else:
                            obj.note = extra
                        changed_fields.append("note")

                if due_at is not None and hasattr(obj, "due_at"):
                    obj.due_at = _parse_dt(due_at)
                    changed_fields.append("due_at")

                if changed_fields:
                    obj.save(update_fields=list(set(changed_fields + ["updated_at"])))
                    updated += 1

        return api_ok({"updated": updated, "ids": ids_int})


class FounderActionEscalateV2Api(BaseApi):
    """
    ✅ V2 auto-escalate (cấp 4)
    POST /api/v1/founder/actions/v2/escalate/

    Rule:
      - action overdue (due_at < now) và chưa closed
      - severity != P0  => bump lên P0
      - status giữ nguyên (open/doing/blocked) để team xử lý

    body json (optional):
    {
      "source": "founder_insight"   # chỉ escalate theo source
      "limit": 50
    }
    """
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_FOUNDER

    def post(self, request):
        if not hasattr(ShopActionItem, "due_at"):
            return api_error("not_supported", "Model chưa có due_at nên không dùng escalate được.", status=400)

        data = request.data or {}
        source = (data.get("source") or "").strip()
        limit = _parse_int(data.get("limit"), default=50) or 50
        limit = max(1, min(limit, 500))

        now = timezone.now()
        qs = ShopActionItem.objects.filter(due_at__lt=now)

        if hasattr(ShopActionItem, "closed_at"):
            qs = qs.filter(closed_at__isnull=True)

        if source and hasattr(ShopActionItem, "source"):
            qs = qs.filter(source=source)

        # chỉ bump cái chưa P0
        qs = qs.exclude(severity=getattr(ShopActionItem, "SEV_P0", "P0")).order_by("due_at")[:limit]

        bumped = 0
        ids: List[int] = []

        with transaction.atomic():
            for obj in qs.select_for_update():
                obj.severity = getattr(ShopActionItem, "SEV_P0", "P0")
                obj.save(update_fields=["severity", "updated_at"])
                bumped += 1
                ids.append(obj.id)

        return api_ok({"bumped": bumped, "ids": ids})