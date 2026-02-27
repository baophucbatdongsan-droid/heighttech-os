from __future__ import annotations

from django.core.cache import cache
from django.db import connection
from rest_framework.permissions import IsAuthenticated

from apps.api.v1.base import BaseApi, api_ok


class SystemHealthApi(BaseApi):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # DB check
        db_ok = True
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                cursor.fetchone()
        except Exception:
            db_ok = False

        # Redis/cache check
        cache_ok = True
        try:
            cache.set("health:ping", "pong", timeout=5)
            cache_ok = cache.get("health:ping") == "pong"
        except Exception:
            cache_ok = False

        status = "ok" if db_ok and cache_ok else "degraded"

        return api_ok({
            "status": status,
            "db": "ok" if db_ok else "fail",
            "cache": "ok" if cache_ok else "fail",
        })