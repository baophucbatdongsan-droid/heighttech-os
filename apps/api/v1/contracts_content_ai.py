from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.contracts.models import ContractChannelContent
from apps.contracts.services_content_ai import score_content


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


class ContentAiScoreApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, content_id: int):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        item = (
            ContractChannelContent.objects_all
            .filter(id=int(content_id), tenant_id=int(tenant_id))
            .prefetch_related("daily_metrics")
            .first()
        )
        if not item:
            return Response({"ok": False, "message": "Không tìm thấy content"}, status=404)

        metrics = []
        try:
            for m in item.daily_metrics.all().order_by("-metric_date")[:14]:
                metrics.append({
                    "views": m.views,
                    "likes": m.likes,
                    "comments": m.comments,
                    "shares": m.shares,
                    "orders": m.orders,
                    "revenue": str(m.revenue or 0),
                })
        except Exception:
            pass

        ai = score_content(metrics)

        return Response({
            "ok": True,
            "content_id": item.id,
            "ai": ai,
        })