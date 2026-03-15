from __future__ import annotations

from django.db.models import Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.insight import _get_tenant_id
from apps.os.models import OSNotification


def _parse_int(v, default=None):
    try:
        if v is None or v == "":
            return default
        return int(v)
    except Exception:
        return default


def _safe_status(v: str) -> str:
    v = (v or "new").strip().lower()

    # alias cũ -> mới
    if v == "unread":
        return "new"

    return v if v in {"new", "read", "archived"} else "new"


class OSNotificationsApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        tenant_id = _get_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        uid = getattr(request.user, "id", None)

        limit = _parse_int(request.query_params.get("limit"), 50) or 50
        limit = max(1, min(200, limit))

        status = _safe_status(request.query_params.get("status") or "new")
        company_id = _parse_int(request.query_params.get("company_id"), None)
        shop_id = _parse_int(request.query_params.get("shop_id"), None)

        qs = OSNotification.objects_all.filter(
            tenant_id=int(tenant_id),
            status=status,
        )

        if company_id:
            qs = qs.filter(company_id=company_id)
        if shop_id:
            qs = qs.filter(shop_id=shop_id)

        qs = qs.filter(
            Q(target_user_id__isnull=True) | Q(target_user_id=uid)
        ).order_by("-created_at", "-id")[:limit]

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
                    "created_at": n.created_at.isoformat() if n.created_at else "",
                    "read_at": n.read_at.isoformat() if n.read_at else None,
                    "entity": {
                        "kind": n.entity_kind,
                        "id": n.entity_id,
                    }
                    if (n.entity_kind and n.entity_id)
                    else None,
                    "company_id": n.company_id,
                    "shop_id": n.shop_id,
                    "target_user_id": n.target_user_id,
                    "target_role": n.target_role,
                    "meta": n.meta or {},
                }
            )

        unread_qs = OSNotification.objects_all.filter(
            tenant_id=int(tenant_id),
            status="new",
        )

        if company_id:
            unread_qs = unread_qs.filter(company_id=company_id)
        if shop_id:
            unread_qs = unread_qs.filter(shop_id=shop_id)

        unread_qs = unread_qs.filter(
            Q(target_user_id__isnull=True) | Q(target_user_id=uid)
        )
        unread_count = unread_qs.count()

        return Response(
            {
                "ok": True,
                "tenant_id": int(tenant_id),
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

        uid = getattr(request.user, "id", None)

        n = OSNotification.objects_all.filter(
            tenant_id=int(tenant_id),
            id=int(notification_id),
        ).first()

        if not n:
            return Response({"ok": False, "message": "Không tìm thấy thông báo"}, status=404)

        if n.target_user_id and uid and int(n.target_user_id) != int(uid):
            return Response({"ok": False, "message": "Không có quyền"}, status=403)

        n.status = "read"
        n.read_at = timezone.now()
        n.save(update_fields=["status", "read_at"])

        return Response(
            {
                "ok": True,
                "id": n.id,
                "status": n.status,
                "read_at": n.read_at.isoformat() if n.read_at else None,
            }
        )