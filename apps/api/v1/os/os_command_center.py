# apps/api/v1/os/os_command_center.py
from __future__ import annotations

from typing import Any, Dict

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.insight import _get_tenant_id

from apps.os.notifications_service import create_notification
from apps.os.models import OSNotification


class OSCommandCenterApi(APIView):
    """
    POST /api/v1/os/command-center/
    body: {"command": "mark-read 12"} | {"command": "notify founder hello"} | {"command":"refresh"}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request: Request):
        tenant_id = _get_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        cmd = (request.data or {}).get("command", "")
        cmd = str(cmd or "").strip()
        if not cmd:
            return Response({"ok": False, "message": "command empty"}, status=400)

        parts = cmd.split()
        head = parts[0].lower()

        if head in {"refresh", "reload"}:
            return Response({"ok": True, "action": "refresh", "ts": timezone.now().isoformat()})

        if head in {"mark-read", "read"}:
            if len(parts) < 2:
                return Response({"ok": False, "message": "usage: mark-read <id>"}, status=400)
            try:
                nid = int(parts[1])
            except Exception:
                return Response({"ok": False, "message": "invalid id"}, status=400)

            n = OSNotification.objects_all.filter(tenant_id=int(tenant_id), id=int(nid)).first()
            if not n:
                return Response({"ok": False, "message": "not found"}, status=404)

            n.status = OSNotification.Status.READ if hasattr(OSNotification, "Status") else "read"
            n.read_at = timezone.now()
            n.save(update_fields=["status", "read_at"])
            return Response({"ok": True, "action": "mark_read", "id": n.id})

        if head in {"notify"}:
            # notify founder <text...>
            if len(parts) < 3:
                return Response({"ok": False, "message": "usage: notify <role|user:ID> <text>"}, status=400)

            target = parts[1]
            text = " ".join(parts[2:]).strip()

            kwargs: Dict[str, Any] = dict(
                tenant_id=int(tenant_id),
                severity="info",
                tieu_de="Command Center",
                noi_dung=text,
                entity_kind="tenant",
                entity_id=int(tenant_id),
            )

            if target.startswith("user:"):
                try:
                    kwargs["target_user_id"] = int(target.split(":", 1)[1])
                except Exception:
                    return Response({"ok": False, "message": "invalid user id"}, status=400)
            else:
                kwargs["target_role"] = target.lower()

            create_notification(**kwargs)
            return Response({"ok": True, "action": "notify", "target": target})

        return Response(
            {
                "ok": False,
                "message": "unknown command",
                "examples": [
                    "refresh",
                    "mark-read 12",
                    "notify founder hello",
                    "notify user:3 ping",
                ],
            },
            status=400,
        )