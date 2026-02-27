# apps/api/v1/founder_insights.py
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date

from rest_framework.permissions import IsAuthenticated

from apps.api.v1.base import BaseApi, api_ok, api_error
from apps.api.v1.permissions import AbilityPermission
from apps.core.policy import VIEW_API_FOUNDER

from apps.api.v1.guards import get_scope_shop_ids, get_scope_company_ids
from apps.intelligence.models import FounderInsightSnapshot, ShopActionItem
from apps.shops.models import Shop


# =====================================================
# HELPERS
# =====================================================

def _jsonify(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
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


def _parse_month_param(month_str: Optional[str]) -> Optional[date]:
    """
    - month="" / None => all-time
    - month="YYYY-MM-01" => date
    """
    s = (month_str or "").strip()
    if not s:
        return None
    d = parse_date(s)
    return d


def _scope_shop_ids_for_user(user) -> set[int]:
    if getattr(user, "is_superuser", False):
        return set()
    return set(get_scope_shop_ids(user) or [])


def _scope_company_ids_for_user(user) -> set[int]:
    if getattr(user, "is_superuser", False):
        return set()
    return set(get_scope_company_ids(user) or [])


def _filter_actions_by_scope(user, qs):
    """
    ShopActionItem đang lưu shop_id dạng int, nên scope check theo:
    - nếu user có shop_ids => filter shop_id__in
    - nếu user có company_ids => suy ra shop ids từ Shop (brand__company)
    """
    if getattr(user, "is_superuser", False):
        return qs

    shop_ids = _scope_shop_ids_for_user(user)
    company_ids = _scope_company_ids_for_user(user)

    if shop_ids:
        return qs.filter(shop_id__in=list(shop_ids))

    if company_ids:
        scoped_shop_ids = list(
            Shop.objects.filter(brand__company_id__in=list(company_ids)).values_list("id", flat=True)
        )
        return qs.filter(shop_id__in=scoped_shop_ids)

    return qs.none()


def _ensure_action_in_scope(user, action: ShopActionItem) -> None:
    if getattr(user, "is_superuser", False):
        return

    shop_ids = _scope_shop_ids_for_user(user)
    company_ids = _scope_company_ids_for_user(user)

    if shop_ids and action.shop_id in shop_ids:
        return

    if company_ids:
        ok = Shop.objects.filter(id=action.shop_id, brand__company_id__in=list(company_ids)).exists()
        if ok:
            return

    from django.core.exceptions import PermissionDenied
    raise PermissionDenied("Forbidden: action out of scope")


# =====================================================
# SNAPSHOTS
# =====================================================

class FounderSnapshotListApi(BaseApi):
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_FOUNDER

    def get(self, request):
        month_str = request.GET.get("month")
        month = _parse_month_param(month_str)

        qs = FounderInsightSnapshot.objects.all()
        qs = qs.filter(month=month) if month is not None else qs.filter(month__isnull=True)

        # paginate
        page, page_size = _get_page_params(request, default_size=20, max_size=200)
        paginator = Paginator(qs.order_by("-generated_at"), page_size)
        page_obj = paginator.get_page(page)

        items = []
        for s in page_obj.object_list:
            alerts = s.alerts or []
            p0 = [a for a in alerts if (a.get("severity") == "P0")]
            items.append({
                "id": s.id,
                "month": s.month.isoformat() if s.month else "",
                "generated_at": s.generated_at.isoformat() if s.generated_at else "",
                "kpi": _jsonify(s.kpi or {}),
                "alerts_count": len(alerts),
                "p0_count": len(p0),
                "forecast": _jsonify(s.forecast or {}),
            })

        meta = {
            "page": page_obj.number,
            "page_size": page_size,
            "total_items": paginator.count,
            "total_pages": paginator.num_pages,
            "has_next": page_obj.has_next(),
            "has_prev": page_obj.has_previous(),
        }

        return api_ok({"items": items}, meta=meta)


class FounderSnapshotDetailApi(BaseApi):
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_FOUNDER

    def get(self, request, snapshot_id: int):
        s = get_object_or_404(FounderInsightSnapshot, pk=snapshot_id)

        data = {
            "id": s.id,
            "month": s.month.isoformat() if s.month else "",
            "generated_at": s.generated_at.isoformat() if s.generated_at else "",
            "kpi": _jsonify(s.kpi or {}),
            "forecast": _jsonify(s.forecast or {}),
            "alerts": _jsonify(s.alerts or []),
            "actions": _jsonify(s.actions or []),
            "insights": _jsonify(s.insights or {}),
            "shop_health": _jsonify(s.shop_health or []),
        }
        return api_ok(data)


# =====================================================
# ACTIONS
# =====================================================

class FounderActionListApi(BaseApi):
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_FOUNDER

    def get(self, request):
        status = (request.GET.get("status") or "").strip()  # open/doing/done
        severity = (request.GET.get("severity") or "").strip()  # P0/P1/P2
        month_str = request.GET.get("month")
        month = _parse_month_param(month_str)
        shop_id = (request.GET.get("shop_id") or "").strip()

        qs = ShopActionItem.objects.all()
        qs = _filter_actions_by_scope(request.user, qs)

        if status:
            qs = qs.filter(status=status)
        if severity:
            qs = qs.filter(severity=severity)
        if month_str is not None:
            # month="" => all-time (null)
            qs = qs.filter(month=month) if month is not None else qs.filter(month__isnull=True)
        if shop_id:
            try:
                qs = qs.filter(shop_id=int(shop_id))
            except Exception:
                pass

        page, page_size = _get_page_params(request, default_size=50, max_size=200)
        paginator = Paginator(qs.order_by("-id"), page_size)
        page_obj = paginator.get_page(page)

        items = []
        for a in page_obj.object_list:
            items.append({
                "id": a.id,
                "month": a.month.isoformat() if a.month else "",
                "shop_id": a.shop_id,
                "shop_name": a.shop_name or "",
                "company_name": a.company_name or "",
                "title": a.title,
                "severity": a.severity,
                "status": a.status,
                "note": a.note or "",
                "payload": _jsonify(a.payload or {}),
                "created_at": a.created_at.isoformat() if a.created_at else "",
                "updated_at": a.updated_at.isoformat() if a.updated_at else "",
            })

        meta = {
            "page": page_obj.number,
            "page_size": page_size,
            "total_items": paginator.count,
            "total_pages": paginator.num_pages,
            "has_next": page_obj.has_next(),
            "has_prev": page_obj.has_previous(),
        }
        return api_ok({"items": items}, meta=meta)


class FounderActionUpdateStatusApi(BaseApi):
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_FOUNDER

    def post(self, request, action_id: int):
        a = get_object_or_404(ShopActionItem, pk=action_id)
        _ensure_action_in_scope(request.user, a)

        status = (request.data.get("status") or "").strip().lower()
        note = (request.data.get("note") or "").strip()

        allowed = {ShopActionItem.STATUS_OPEN, ShopActionItem.STATUS_DOING, ShopActionItem.STATUS_DONE}
        if status not in allowed:
            return api_error("bad_status", "status không hợp lệ (open/doing/done)", status=400)

        a.status = status
        if note:
            a.note = note
        a.save(update_fields=["status", "note", "updated_at"])

        return api_ok({
            "id": a.id,
            "status": a.status,
            "note": a.note or "",
            "updated_at": a.updated_at.isoformat() if a.updated_at else "",
        })