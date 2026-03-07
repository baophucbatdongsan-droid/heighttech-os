# apps/api/v1/os/os_notifications.py
from __future__ import annotations

from typing import Optional

from django.db import models
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.insight import _get_tenant_id
from apps.core.permissions import resolve_user_role
from apps.os.models import OSNotification
from apps.os.notification_targeting import build_target_q, apply_scope_filters


def _parse_int(v, default=None):
    try:
        if v is None or v == "":
            return default
        return int(v)
    except Exception:
        return default


def _safe_status(v: str) -> str:
    v = (v or "new").strip().lower()
    return v if v in {"new", "read", "archived"} else "new"


class OSNotificationsApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        tenant_id = _get_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        role = (resolve_user_role(request.user) or "operator").strip().lower()
        uid = getattr(request.user, "id", None)

        limit = _parse_int(request.query_params.get("limit"), 50) or 50
        limit = max(1, min(200, limit))

        status = _safe_status(request.query_params.get("status") or "new")
        company_id = _parse_int(request.query_params.get("company_id"), None)
        shop_id = _parse_int(request.query_params.get("shop_id"), None)
        project_id = _parse_int(request.query_params.get("project_id"), None)

        qs = OSNotification.objects_all.filter(tenant_id=int(tenant_id), status=status)

        # targeting
        tq = build_target_q(Model=OSNotification, user_id=uid, role=role)
        qs = qs.filter(tq)

        # scope filters (chỉ apply nếu model có field)
        qs = apply_scope_filters(qs=qs, company_id=company_id, shop_id=shop_id, project_id=project_id)

        qs = qs.order_by("-created_at", "-id")[:limit]

        items = []
        for n in qs:
            items.append(
                {
                    "id": n.id,
                    "tieu_de": n.tieu_de,
                    "noi_dung": n.noi_dung,
                    "severity": n.severity,
                    "status": n.status,
                    "thoi_gian": n.created_at.isoformat() if n.created_at else "",
                    "read_at": n.read_at.isoformat() if n.read_at else None,
                    "entity": {"kind": n.entity_kind, "id": n.entity_id} if (n.entity_kind and n.entity_id) else None,
                    "company_id": getattr(n, "company_id", None),
                    "shop_id": getattr(n, "shop_id", None),
                    "project_id": getattr(n, "project_id", None),
                    "meta": n.meta or {},
                }
            )

        # unread_count theo targeting + scope (chuẩn cho badge FE)
        unread_qs = OSNotification.objects_all.filter(tenant_id=int(tenant_id), status="new").filter(tq)
        unread_qs = apply_scope_filters(qs=unread_qs, company_id=company_id, shop_id=shop_id, project_id=project_id)
        unread_count = unread_qs.count()

        return Response(
            {
                "ok": True,
                "tenant_id": int(tenant_id),
                "role": role,
                "status": status,
                "limit": limit,
                "unread_count": unread_count,
                "items": items,
                "generated_at": timezone.now().isoformat(),
            }
        )


class OSNotificationMarkReadApi(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, notification_id: int):
        tenant_id = _get_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        role = (resolve_user_role(request.user) or "operator").strip().lower()
        uid = getattr(request.user, "id", None)

        n = OSNotification.objects_all.filter(tenant_id=int(tenant_id), id=int(notification_id)).first()
        if not n:
            return Response({"ok": False, "message": "Không tìm thấy thông báo"}, status=404)

        # chỉ cho phép mark nếu user thuộc target (user/role/public)
        allowed = False
        if getattr(n, "target_user_id", None) and uid and int(n.target_user_id) == int(uid):
            allowed = True
        elif (getattr(n, "target_role", "") or "").strip().lower() == role and (getattr(n, "target_role", "") or "").strip():
            allowed = True
        elif (getattr(n, "target_user_id", None) is None) and ((getattr(n, "target_role", "") or "") == ""):
            allowed = True

        if not allowed:
            return Response({"ok": False, "message": "Không có quyền"}, status=403)

        n.status = OSNotification.Status.READ if hasattr(OSNotification, "Status") else "read"
        n.read_at = timezone.now()
        n.save(update_fields=["status", "read_at"])
        return Response({"ok": True, "id": n.id, "status": n.status, "read_at": n.read_at.isoformat()})