# apps/api/v1/os_dashboard.py
from __future__ import annotations

from typing import Optional

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .insight import FounderInsightApi, _get_tenant_id


class OSDashboardApi(APIView):
    """
    /api/v1/os/dashboard/

    Mục tiêu:
    - 1 endpoint trung tâm cho FE
    - Không phụ thuộc model "Performance"
    - Reuse FounderInsightApi (khỏi duplicate logic)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant_id = _get_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "tenant_id missing"}, status=400)

        # Reuse trực tiếp insight payload
        insight_resp = FounderInsightApi().get(request)
        try:
            insight_data = getattr(insight_resp, "data", None) or {}
        except Exception:
            insight_data = {}

        now = timezone.now()

        return Response(
            {
                "ok": True,
                "generated_at": now.isoformat(),
                "tenant_id": tenant_id,

                # section: center blocks
                "center": {
                    "insight": insight_data,
                },

                # quick extracts for FE dễ vẽ card
                "overview": (insight_data.get("overview") or {}),
                "alerts": (insight_data.get("alerts") or []),
                "recommendations": (insight_data.get("recommendations") or []),
                "shops": (insight_data.get("shops") or []),
            }
        )