# apps/api/v1/os/os_work_assign_by.py
from __future__ import annotations

from typing import Optional

from django.contrib.auth import get_user_model
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.insight import _get_tenant_id

try:
    from apps.work.models import WorkItem
except Exception:
    WorkItem = None

User = get_user_model()


# ✅ miễn CSRF cho session-auth (OS UI gọi fetch POST)
class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        return  # skip CSRF check


def _pick_user(q: str) -> Optional[User]:
    s = (q or "").strip()
    if not s:
        return None

    u = User.objects.filter(email__iexact=s).first()
    if u:
        return u

    if hasattr(User, "username"):
        u = User.objects.filter(username__iexact=s).first()
        if u:
            return u

    u = User.objects.filter(email__icontains=s).first()
    if u:
        return u

    if hasattr(User, "username"):
        u = User.objects.filter(username__icontains=s).first()
        if u:
            return u

    return None


class OSWorkAssignByApi(APIView):
    """
    POST /api/v1/os/work/assign-by/
    body: { task_id, q }   # q = email/username
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication, TokenAuthentication]

    def post(self, request):
        tenant_id = _get_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)
        tenant_id = int(tenant_id)

        if WorkItem is None:
            return Response({"ok": False, "message": "WorkItem not found"}, status=501)

        payload = request.data or {}
        task_id = payload.get("task_id")
        q = (payload.get("q") or "").strip()

        try:
            task_id = int(task_id)
        except Exception:
            return Response({"ok": False, "message": "task_id không hợp lệ"}, status=400)

        user = _pick_user(q)
        if not user:
            return Response({"ok": False, "message": "Không tìm thấy user theo email/username"}, status=404)

        qs = WorkItem.objects_all if hasattr(WorkItem, "objects_all") else WorkItem.objects
        item = qs.filter(tenant_id=tenant_id, id=task_id).first()
        if not item:
            return Response({"ok": False, "message": "Task not found"}, status=404)

        item.assignee_id = int(user.id)

        # ✅ update_fields đúng field
        try:
            item.save(update_fields=["assignee_id", "updated_at"])
        except Exception:
            item.save()

        return Response({"ok": True, "task_id": task_id, "assignee_id": int(user.id)})