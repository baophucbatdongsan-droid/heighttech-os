# apps/api/v1/ops_owners.py
from __future__ import annotations

from django.utils.dateparse import parse_date
from rest_framework.permissions import IsAuthenticated

from apps.api.v1.base import BaseApi, api_ok, api_error
from apps.api.v1.permissions import AbilityPermission
from apps.core.policy import VIEW_API_FOUNDER

from apps.intelligence.ops_metrics import calc_owner_performance


class FounderOpsOwnerPerformanceApi(BaseApi):
    """
    GET /api/v1/founder/ops/owners/performance/?days=30&month=2026-02-01&owner_ids=1,2,3
    """
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_FOUNDER

    def get(self, request):
        month_str = (request.GET.get("month") or "").strip()
        days_str = (request.GET.get("days") or "30").strip()
        owner_ids_str = (request.GET.get("owner_ids") or "").strip()

        month = None
        if month_str:
            month = parse_date(month_str)
            if not month:
                return api_error("bad_month", "month phải là YYYY-MM-DD (vd 2026-02-01)", status=400)

        try:
            days = int(days_str)
        except Exception:
            days = 30

        owner_ids = None
        if owner_ids_str:
            parts = [p.strip() for p in owner_ids_str.split(",")]
            owner_ids = []
            for p in parts:
                if not p:
                    continue
                try:
                    owner_ids.append(int(p))
                except Exception:
                    continue

        payload = calc_owner_performance(month=month, days=days, owner_ids=owner_ids)
        return api_ok(payload)