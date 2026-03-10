from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.contracts.services_recompute_engine import recompute_content_engine


def _tenant_id_from_request(request):
    tid = request.headers.get("X-Tenant-Id")
    if tid:
        try:
            return int(tid)
        except Exception:
            pass

    tenant = getattr(request, "tenant", None)
    tid = getattr(tenant, "id", None) if tenant else None
    if tid:
        try:
            return int(tid)
        except Exception:
            pass

    tid = getattr(request, "tenant_id", None)
    if tid:
        try:
            return int(tid)
        except Exception:
            pass

    return None


class FounderContentRecomputeApi(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        limit = request.data.get("limit", 300)
        try:
            limit = int(limit)
        except Exception:
            limit = 300

        result = recompute_content_engine(
            tenant_id=int(tenant_id),
            limit=limit,
        )

        return Response({
            "ok": True,
            "tenant_id": int(tenant_id),
            **result,
        })