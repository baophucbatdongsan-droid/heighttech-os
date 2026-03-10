from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.contracts.services_content_work_sync import sync_content_from_workitem
from apps.work.models import WorkItem


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


class ContentSyncFromWorkItemApi(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, workitem_id: int):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        wi = WorkItem.objects_all.filter(
            id=int(workitem_id),
            tenant_id=int(tenant_id),
        ).first()
        if not wi:
            return Response({"ok": False, "message": "Không tìm thấy workitem"}, status=404)

        content = sync_content_from_workitem(wi)

        if not content:
            return Response({
                "ok": False,
                "message": "Workitem này không gắn contract_channel_content",
            }, status=400)

        return Response({
            "ok": True,
            "workitem_id": wi.id,
            "content_id": content.id,
            "content_status": content.status,
            "aired_at": content.aired_at.isoformat() if content.aired_at else None,
        })