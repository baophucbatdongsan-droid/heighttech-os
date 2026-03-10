from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.contracts.services_assignment_intelligence import (
    infer_role_key_from_task,
    pick_assignee_for_role,
)


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


class FounderAssignmentPreviewApi(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        data = request.data or {}
        title = str(data.get("title") or "")
        description = str(data.get("description") or "")
        priority_label = str(data.get("priority_label") or "")

        role_key = infer_role_key_from_task(
            title=title,
            description=description,
            priority_label=priority_label,
        )
        user = pick_assignee_for_role(
            tenant_id=int(tenant_id),
            role_key=role_key,
        )

        return Response({
            "ok": True,
            "role_key": role_key,
            "assignee": {
                "id": getattr(user, "id", None),
                "username": getattr(user, "username", "") if user else "",
                "email": getattr(user, "email", "") if user else "",
            } if user else None,
        })