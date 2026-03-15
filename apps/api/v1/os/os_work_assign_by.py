from __future__ import annotations

from typing import Optional

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.insight import _get_tenant_id
from apps.events.bus import emit_event, make_dedupe_key

try:
    from apps.work.models import WorkItem
except Exception:
    WorkItem = None

User = get_user_model()


class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        return


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


def _safe_rel_name(obj, fallback=""):
    try:
        if not obj:
            return fallback
        if hasattr(obj, "name") and obj.name:
            return str(obj.name)
        if hasattr(obj, "title") and obj.title:
            return str(obj.title)
        if hasattr(obj, "username") and obj.username:
            return str(obj.username)
        if hasattr(obj, "email") and obj.email:
            return str(obj.email)
        return fallback
    except Exception:
        return fallback


def _iso(dt):
    try:
        return dt.isoformat() if dt else None
    except Exception:
        return None


def _serialize_item(w):
    assignee = getattr(w, "assignee", None)
    company = getattr(w, "company", None)
    shop = getattr(w, "shop", None)
    project = getattr(w, "project", None)

    return {
        "id": w.id,
        "title": getattr(w, "title", "") or "",
        "description": getattr(w, "description", "") or "",
        "status": getattr(w, "status", "") or "",
        "rank": getattr(w, "rank", "") or "",
        "priority": int(getattr(w, "priority", 0) or 0),
        "tenant_id": getattr(w, "tenant_id", None),
        "company_id": getattr(w, "company_id", None),
        "project_id": getattr(w, "project_id", None),
        "shop_id": getattr(w, "shop_id", None),
        "company_name": _safe_rel_name(company, ""),
        "shop_name": _safe_rel_name(shop, ""),
        "project_name": _safe_rel_name(project, ""),
        "assignee_id": getattr(w, "assignee_id", None),
        "assignee_name": (
            getattr(assignee, "get_full_name", lambda: "")()
            or getattr(assignee, "username", "")
            or getattr(assignee, "email", "")
        ) if assignee else "",
        "assignee_email": getattr(assignee, "email", "") if assignee else "",
        "requester_id": getattr(w, "requester_id", None),
        "created_by_id": getattr(w, "created_by_id", None),
        "target_type": getattr(w, "target_type", "") or "",
        "target_id": getattr(w, "target_id", None),
        "due_at": _iso(getattr(w, "due_at", None)),
        "created_at": _iso(getattr(w, "created_at", None)),
        "updated_at": _iso(getattr(w, "updated_at", None)),
    }


class OSWorkAssignByApi(APIView):
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

        qs = (
            WorkItem.objects_all
            .select_related("assignee", "requester", "project", "shop", "company")
        )
        item = qs.filter(tenant_id=tenant_id, id=task_id).first()
        if not item:
            return Response({"ok": False, "message": "Task not found"}, status=404)

        old_assignee_id = getattr(item, "assignee_id", None)
        item.assignee_id = int(user.id)

        try:
            item.save(update_fields=["assignee_id", "updated_at"])
        except Exception:
            item.save()

        if int(user.id) != int(old_assignee_id or 0):
            try:
                payload = {
                    "id": item.id,
                    "work_item_id": item.id,
                    "title": getattr(item, "title", ""),
                    "status": getattr(item, "status", ""),
                    "assignee_id": item.assignee_id,
                    "old_assignee_id": old_assignee_id,
                }

                dedupe = make_dedupe_key(
                    name="work.item.assigned",
                    tenant_id=tenant_id,
                    entity="workitem",
                    entity_id=item.id,
                    extra={
                        "assignee_id": str(item.assignee_id or ""),
                        "updated_at": item.updated_at.isoformat() if getattr(item, "updated_at", None) else "",
                    },
                )

                transaction.on_commit(
                    lambda: emit_event(
                        tenant_id=tenant_id,
                        company_id=getattr(item, "company_id", None),
                        shop_id=getattr(item, "shop_id", None),
                        actor_id=getattr(request.user, "id", None),
                        name="work.item.assigned",
                        version=1,
                        dedupe_key=dedupe,
                        payload=payload,
                    )
                )
            except Exception:
                pass

        item.refresh_from_db()
        item = (
            WorkItem.objects_all
            .select_related("assignee", "requester", "project", "shop", "company")
            .get(id=item.id)
        )

        return Response({
            "ok": True,
            "task_id": task_id,
            "assignee_id": int(user.id),
            "item": _serialize_item(item),
        })