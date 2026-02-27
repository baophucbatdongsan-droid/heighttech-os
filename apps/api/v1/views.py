# apps/api/v1/views.py
from __future__ import annotations

from rest_framework.views import APIView

from apps.api.v1.base import api_ok


class ApiV1Root(APIView):
    def get(self, request):
        return api_ok(
            {
                "dashboard": "/api/v1/dashboard/",
                "founder": "/api/v1/founder/",
                "founder_shop": "/api/v1/founder/shops/<id>/",
            }
        )