# apps/api/os_dashboard.py
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class OSDashboardApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return Response(
            {
                "ok": True,
                "message": "OS Dashboard API is alive",
            }
        )