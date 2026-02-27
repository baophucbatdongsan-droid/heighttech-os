from __future__ import annotations
from rest_framework.views import APIView
from apps.api.v1.base import api_ok

class ApiRoot(APIView):
    def get(self, request):
        return api_ok({
            "v1": "/api/v1/",
            "endpoints": [
                "/api/v1/dashboard/",
                "/api/v1/founder/",
                "/api/v1/founder/shops/<id>/",
            ],
        })