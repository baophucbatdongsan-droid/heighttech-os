from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Tuple

from django.core.paginator import Paginator
from django.db.models.query import QuerySet
from django.shortcuts import get_object_or_404

from rest_framework.permissions import IsAuthenticated

from apps.api.v1.base import BaseApi, api_ok
from apps.api.v1.guards import ensure_can_access_shop
from apps.api.v1.permissions import AbilityPermission
from apps.api.v1.serializers import (
    serialize_monthly_performance,
    serialize_shop,
    serialize_shop_health_row,
)
from apps.core.policy import VIEW_API_FOUNDER
from apps.core.permissions import resolve_company_scope_for_request
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


class FounderDashboardApi(BaseApi):
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_FOUNDER

    def get(self, request):
        month = request.GET.get("month")

        # agency/founder có thể ignore company scope, nhưng mình vẫn trả meta cho FE nếu muốn filter
        selected_company_id, allowed_company_ids = resolve_company_scope_for_request(request)

        ctx = FounderIntelligenceService.build_founder_context(month=month)

        rows = ctx.get("shop_health") or []
        rows = [serialize_shop_health_row(x) for x in rows]

        page, page_size = _get_page_params(request, default_size=50, max_size=200)
        paginator = Paginator(rows, page_size)
        page_obj = paginator.get_page(page)

        ctx["shop_health"] = list(page_obj.object_list)
        ctx["top_companies"] = _jsonify(ctx.get("top_companies") or [])
        ctx["loss_companies"] = _jsonify(ctx.get("loss_companies") or [])

        # optional meta for UI
        ctx["company_scope"] = {
            "selected_company_id": selected_company_id,
            "allowed_company_ids": allowed_company_ids,
        }

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


class FounderShopDetailApi(BaseApi):
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_FOUNDER

    def get(self, request, shop_id: int):
        shop = get_object_or_404(Shop, pk=shop_id)

        # ✅ object-level guard (tránh leak dữ liệu shop ngoài scope)
        ensure_can_access_shop(request.user, shop)

        month = request.GET.get("month")
        page, page_size = _get_page_params(request, default_size=50, max_size=200)

        ctx = FounderIntelligenceService.build_shop_deep_context(shop=shop, month=month)

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