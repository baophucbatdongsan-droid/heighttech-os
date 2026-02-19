# apps/api/v1/ops_health.py
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Set

from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_date

from rest_framework.permissions import IsAuthenticated

from apps.api.v1.base import BaseApi, api_ok
from apps.api.v1.permissions import AbilityPermission
from apps.core.policy import VIEW_API_FOUNDER
from apps.intelligence.models import ShopActionItem

# ---- Optional: tier guard (nếu project có) ----
try:
    from apps.core.tier_guard import require_tier  # type: ignore
    from apps.tenants.models_subscription import SubscriptionTier  # type: ignore
except Exception:  # fallback nếu bạn chưa có module/tier
    require_tier = None  # type: ignore
    SubscriptionTier = None  # type: ignore


# =========================
# Helpers
# =========================

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


OPEN_STATUSES: Set[str] = {
    getattr(ShopActionItem, "STATUS_OPEN", "open"),
    getattr(ShopActionItem, "STATUS_DOING", "doing"),
    getattr(ShopActionItem, "STATUS_BLOCKED", "blocked"),
}


# =========================
# API
# =========================

class FounderOpsHealthApi(BaseApi):
    """
    GET /api/v1/ops/health/?month=2026-02-01

    Trả về "Ops Command Center" metrics:
    - tổng open actions theo severity
    - overdue / blocked
    - owner load
    - top risky shops
    """

    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_FOUNDER

    # nếu có tier guard thì bật, không có thì bỏ qua
    if require_tier and SubscriptionTier:
        @require_tier(SubscriptionTier.PRO)  # type: ignore
        def get(self, request):
            return self._get_impl(request)
    else:
        def get(self, request):
            return self._get_impl(request)

    def _get_impl(self, request):
        month_str = (request.GET.get("month") or "").strip()
        month = parse_date(month_str) if month_str else None

        qs = ShopActionItem.objects.all()
        if month:
            qs = qs.filter(month=month)

        open_qs = qs.filter(status__in=list(OPEN_STATUSES))
        now = timezone.now()

        # =========================
        # Summary
        # =========================
        total_open = open_qs.count()
        total_p0 = open_qs.filter(severity="P0").count()
        total_p1 = open_qs.filter(severity="P1").count()
        total_p2 = open_qs.filter(severity="P2").count()

        overdue = 0
        if hasattr(ShopActionItem, "due_at"):
            overdue = open_qs.filter(due_at__lt=now).count()

        blocked_status = getattr(ShopActionItem, "STATUS_BLOCKED", "blocked")
        blocked = open_qs.filter(status=blocked_status).count()

        # =========================
        # Owner load (nếu model có owner)
        # =========================
        owner_load = []
        if hasattr(ShopActionItem, "owner_id"):
            owner_load = list(
                open_qs
                .exclude(owner_id__isnull=True)
                .values("owner_id")
                .annotate(
                    total=Count("id"),
                    p0=Count("id", filter=Q(severity="P0")),
                    p1=Count("id", filter=Q(severity="P1")),
                )
                .order_by("-p0", "-p1", "-total")
            )

        # =========================
        # Top risk shops
        # =========================
        shop_risk = list(
            open_qs
            .values("shop_id", "shop_name")
            .annotate(
                total=Count("id"),
                p0=Count("id", filter=Q(severity="P0")),
                p1=Count("id", filter=Q(severity="P1")),
            )
            .order_by("-p0", "-p1", "-total")[:10]
        )

        payload: Dict[str, Any] = {
            "month": month_str or "all",
            "generated_at": timezone.now(),
            "summary": {
                "total_open": total_open,
                "p0": total_p0,
                "p1": total_p1,
                "p2": total_p2,
                "overdue": overdue,
                "blocked": blocked,
            },
            "owner_load": owner_load,
            "top_risk_shops": shop_risk,
        }

        return api_ok(_jsonify(payload))


# ✅ Alias giữ tương thích nếu chỗ khác import OpsHealthApi
OpsHealthApi = FounderOpsHealthApi