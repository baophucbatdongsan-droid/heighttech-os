# apps/api/v1/client.py
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Tuple, Optional, List

from django.core.paginator import Paginator
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404

from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied

from apps.api.v1.base import BaseApi, api_ok
from apps.api.v1.permissions import AbilityPermission
from apps.api.v1.guards import (
    filter_shops_queryset_for_user,
    ensure_can_access_shop,
    get_scope_company_ids,
)
from apps.api.v1.serializers import (
    serialize_shop,
    serialize_monthly_performance,
)
from apps.core.policy import VIEW_API_DASHBOARD
from apps.core.permissions import is_founder
from apps.intelligence.services import FounderIntelligenceService
from apps.shops.models import Shop


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


def _get_header_company_id(request) -> Optional[int]:
    raw = (
        request.headers.get("X-Company-Id")
        or request.META.get("HTTP_X_COMPANY_ID")
        or ""
    ).strip()
    if not raw:
        return None
    try:
        return int(raw)
    except Exception:
        return None


def _resolve_company_scope_for_request(request) -> tuple[Optional[int], List[int]]:
    """
    Return (selected_company_id, allowed_company_ids)

    Rule:
    - superuser/founder: selected_company_id = header (nếu có) else None (all)
    - user thường: allowed_company_ids lấy từ scope.
        - Nếu header có: phải nằm trong allowed
        - Nếu header không có:
            - nếu allowed rỗng: chưa được gán
            - nếu allowed có: bắt chọn (để tránh lẫn data giữa companies)
    """
    user = request.user
    header_cid = _get_header_company_id(request)

    # founder/superuser => không cần ép
    if getattr(user, "is_superuser", False) or is_founder(user):
        return header_cid, []

    allowed = list(get_scope_company_ids(user) or [])

    if header_cid is None:
        return None, allowed

    if header_cid not in allowed:
        raise PermissionDenied("Forbidden: company out of scope")

    return header_cid, allowed


class ClientDashboardApi(BaseApi):
    """
    Dashboard cho client/agency member:
    - ép theo company scope (X-Company-Id) với user không phải founder
    - chỉ xem shop thuộc scope + company đó
    - trả kèm MonthlyPerformance + profit_breakdown
    """
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def get(self, request):
        selected_company_id, allowed_company_ids = _resolve_company_scope_for_request(request)

        # user thường: nếu có allowed list mà chưa chọn company => bắt chọn
        if selected_company_id is None and allowed_company_ids:
            raise PermissionDenied("Missing X-Company-Id. Bạn cần chọn Company để xem dashboard.")

        # user thường: không có allowed => chưa được gán quyền
        if selected_company_id is None and not allowed_company_ids and not (
            getattr(request.user, "is_superuser", False) or is_founder(request.user)
        ):
            return api_ok(
                {
                    "message": "Bạn chưa được gán Company/Shop nào. Liên hệ quản trị để cấp quyền.",
                    "company_id": None,
                    "shop": None,
                    "items": [],
                    "shops_in_scope": [],
                }
            )

        # 1) shop scope theo user
        shops_qs = filter_shops_queryset_for_user(
            request.user,
            Shop.objects.all()
        ).select_related("brand", "brand__company")

        # 2) ép company scope nếu đã chọn
        if selected_company_id:
            shops_qs = shops_qs.filter(brand__company_id=selected_company_id)

        # 3) chọn shop (query param shop_id hoặc shop đầu tiên)
        shop_id_raw = (request.GET.get("shop_id") or "").strip()
        if shop_id_raw:
            try:
                shop_id = int(shop_id_raw)
            except Exception:
                shop_id = 0
            shop = get_object_or_404(shops_qs, pk=shop_id)
        else:
            shop = shops_qs.order_by("id").first()

        if not shop:
            return api_ok(
                {
                    "message": "Company này chưa có shop nào (hoặc bạn chưa có quyền).",
                    "company_id": selected_company_id,
                    "shop": None,
                    "items": [],
                    "shops_in_scope": [],
                }
            )

        # 4) object-level guard
        ensure_can_access_shop(request.user, shop)

        month = request.GET.get("month")
        page, page_size = _get_page_params(request, default_size=50, max_size=200)

        # 5) context theo shop
        ctx = FounderIntelligenceService.build_shop_deep_context(shop=shop, month=month)

        # 6) serialize
        ctx["company_id"] = selected_company_id
        ctx["shop"] = serialize_shop(ctx.get("shop"))

        items = ctx.get("items") or []
        items = [serialize_monthly_performance(x) for x in items]

        paginator = Paginator(items, page_size)
        page_obj = paginator.get_page(page)
        ctx["items"] = list(page_obj.object_list)

        latest = ctx["items"][0] if ctx["items"] else {}
        ctx["profit_breakdown"] = {
            "gmv": latest.get("revenue", 0.0),
            "chi_phi": latest.get("cost", 0.0),
            "profit_base": latest.get("profit", 0.0),
            "company_net_profit": latest.get("company_net_profit", 0.0),
        }

        ctx["shops_in_scope"] = [serialize_shop(s) for s in shops_qs.order_by("id")[:200]]
        ctx = _jsonify(ctx)

        meta = {
            "page": page_obj.number,
            "page_size": page_size,
            "total_items": paginator.count,
            "total_pages": paginator.num_pages,
            "has_next": page_obj.has_next(),
            "has_prev": page_obj.has_previous(),
        }
        return api_ok(ctx, meta=meta)