from __future__ import annotations

from typing import Any, Dict, Optional

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.insight import _get_tenant_id


def _safe_import_workitem_model():
    try:
        m = __import__("apps.work.models", fromlist=["WorkItem"])
        return getattr(m, "WorkItem")
    except Exception:
        return None


WorkItem = _safe_import_workitem_model()


class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        return


def _parse_int(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        return int(s)
    except Exception:
        return None


def _iso(dt):
    try:
        return dt.isoformat() if dt else None
    except Exception:
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


def _serialize_item(w) -> Dict[str, Any]:
    assignee = getattr(w, "assignee", None)
    company = getattr(w, "company", None)
    shop = getattr(w, "shop", None)
    project = getattr(w, "project", None)

    return {
        "id": w.id,
        "title": getattr(w, "title", "") or "",
        "description": getattr(w, "description", "") or "",
        "status": getattr(w, "status", "") or "",
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
        "due_at": _iso(getattr(w, "due_at", None)),
        "created_at": _iso(getattr(w, "created_at", None)),
        "updated_at": _iso(getattr(w, "updated_at", None)),
    }


def _apply_open_filter(qs, status: str):
    st = (status or "open").strip().lower()

    if st in ("board", "all"):
        return qs.exclude(status="cancelled"), "board"

    if st in ("open", "new", "in_progress", "pending"):
        return qs.exclude(status__in=["done", "cancelled"]), "open"

    if st in ("todo", "doing", "blocked"):
        return qs.filter(status=st), st

    if st in ("done", "closed", "completed"):
        return qs.filter(status="done"), "done"

    if st in ("cancelled", "canceled"):
        return qs.filter(status="cancelled"), "cancelled"

    return qs, st


def _parse_due_at(raw):
    if not raw:
        return None

    dt = parse_datetime(str(raw))
    if dt and timezone.is_naive(dt):
        try:
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        except Exception:
            pass
    return dt


def _reload_item(obj):
    try:
        return (
            WorkItem.objects_all.select_related(
                "assignee",
                "requester",
                "created_by",
                "company",
                "shop",
                "project",
            ).get(id=obj.id)
        )
    except Exception:
        return obj


class OSWorkInboxApi(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication, TokenAuthentication]

    def get(self, request):
        tenant_id = _get_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        tenant_id = int(tenant_id)

        if WorkItem is None:
            return Response(
                {
                    "ok": True,
                    "generated_at": timezone.now().isoformat(),
                    "tenant_id": tenant_id,
                    "items": [],
                    "open_count": 0,
                    "note": "WorkItem model not found.",
                }
            )

        scope = (request.query_params.get("scope") or "tenant").strip().lower()
        company_id = _parse_int(request.query_params.get("company_id"))
        shop_id = _parse_int(request.query_params.get("shop_id"))
        project_id = _parse_int(request.query_params.get("project_id"))
        assignee = request.query_params.get("assignee")
        status = (request.query_params.get("status") or "open").strip().lower()

        try:
            limit = int(request.query_params.get("limit") or 20)
        except Exception:
            limit = 20
        limit = max(1, min(100, limit))

        qs = WorkItem.objects_all.all() if hasattr(WorkItem, "objects_all") else WorkItem.objects.all()
        qs = qs.filter(tenant_id=tenant_id)

        try:
            qs = qs.select_related("assignee", "requester", "created_by", "company", "shop", "project")
        except Exception:
            pass

        if scope == "company":
            if not company_id:
                return Response({"ok": False, "message": "scope=company cần company_id"}, status=400)
            qs = qs.filter(company_id=company_id)

        if scope == "shop":
            if not shop_id:
                return Response({"ok": False, "message": "scope=shop cần shop_id"}, status=400)
            qs = qs.filter(shop_id=shop_id)

        if scope == "project":
            if not project_id:
                return Response({"ok": False, "message": "scope=project cần project_id"}, status=400)
            qs = qs.filter(project_id=project_id)

        if assignee:
            try:
                qs = qs.filter(assignee_id=int(assignee))
            except Exception:
                return Response({"ok": False, "message": "assignee không hợp lệ"}, status=400)

        qs, normalized_status = _apply_open_filter(qs, status)

        try:
            open_count = int(qs.count())
        except Exception:
            open_count = 0

        qs = qs.order_by("-updated_at", "-id")
        items = [_serialize_item(x) for x in qs[:limit]]

        return Response(
            {
                "ok": True,
                "generated_at": timezone.now().isoformat(),
                "tenant_id": tenant_id,
                "scope": scope,
                "status": normalized_status,
                "items": items,
                "open_count": open_count,
            }
        )


class OSWorkCreateApi(APIView):
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
        title = (payload.get("title") or "").strip()
        if not title:
            return Response({"ok": False, "message": "Thiếu title"}, status=400)

        obj = WorkItem()
        obj.tenant_id = tenant_id
        obj.title = title
        obj.description = (payload.get("description") or "").strip()

        raw_status = (payload.get("status") or "todo").strip().lower()
        obj.status = raw_status if raw_status in ("todo", "doing", "blocked", "done", "cancelled") else "todo"

        pr = _parse_int(payload.get("priority"))
        obj.priority = pr if pr in (1, 2, 3, 4) else 2

        for k in ("company_id", "shop_id", "project_id"):
            v = _parse_int(payload.get(k))
            if hasattr(obj, k):
                setattr(obj, k, v)

        due_at = _parse_due_at(payload.get("due_at") or payload.get("deadline"))
        if due_at:
            obj.due_at = due_at

        uid = getattr(getattr(request, "user", None), "id", None)
        if uid:
            obj.created_by_id = int(uid)

        aid = _parse_int(payload.get("assignee_id"))
        if aid is not None:
            obj.assignee_id = aid
        elif uid:
            obj.assignee_id = int(uid)

        obj.save()
        obj = _reload_item(obj)

        return Response({"ok": True, "item": _serialize_item(obj)}, status=201)


class OSWorkAssignApi(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication, TokenAuthentication]

    def post(self, request, task_id: int):
        tenant_id = _get_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)
        tenant_id = int(tenant_id)

        if WorkItem is None:
            return Response({"ok": False, "message": "WorkItem not found"}, status=501)

        assignee_id = _parse_int((request.data or {}).get("assignee_id"))
        if not assignee_id:
            return Response({"ok": False, "message": "assignee_id không hợp lệ"}, status=400)

        qs = WorkItem.objects_all.all() if hasattr(WorkItem, "objects_all") else WorkItem.objects.all()
        obj = qs.filter(tenant_id=tenant_id, id=int(task_id)).first()
        if not obj:
            return Response({"ok": False, "message": "Task not found"}, status=404)

        obj.assignee_id = int(assignee_id)
        try:
            obj.save(update_fields=["assignee_id", "updated_at"])
        except Exception:
            obj.save()

        obj = _reload_item(obj)
        return Response({"ok": True, "item": _serialize_item(obj)})


class OSWorkMoveApi(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication, TokenAuthentication]

    def post(self, request, task_id: int):
        tenant_id = _get_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)
        tenant_id = int(tenant_id)

        if WorkItem is None:
            return Response({"ok": False, "message": "WorkItem not found"}, status=501)

        payload = request.data or {}
        to_status = (payload.get("status") or "").strip().lower()
        to_company = _parse_int(payload.get("company_id"))
        to_shop = _parse_int(payload.get("shop_id"))

        if to_status and to_status not in ("todo", "doing", "blocked", "done", "cancelled"):
            return Response({"ok": False, "message": "status không hợp lệ"}, status=400)

        qs = WorkItem.objects_all.all() if hasattr(WorkItem, "objects_all") else WorkItem.objects.all()
        obj = qs.filter(tenant_id=tenant_id, id=int(task_id)).first()
        if not obj:
            return Response({"ok": False, "message": "Task not found"}, status=404)

        if to_status:
            obj.status = to_status
        if hasattr(obj, "company_id"):
            obj.company_id = to_company
        if hasattr(obj, "shop_id"):
            obj.shop_id = to_shop

        try:
            fields = ["updated_at"]
            if to_status:
                fields.append("status")
            if hasattr(obj, "company_id"):
                fields.append("company_id")
            if hasattr(obj, "shop_id"):
                fields.append("shop_id")
            obj.save(update_fields=fields)
        except Exception:
            obj.save()

        obj = _reload_item(obj)
        return Response({"ok": True, "item": _serialize_item(obj)})


class OSWorkUpdateApi(APIView):
    """
    POST /api/v1/os/work/<int:task_id>/update/
    body:
    {
      "title": "...",
      "description": "...",
      "priority": 1..4,
      "due_at": "...",
      "status": "todo|doing|blocked|done|cancelled",
      "assignee_id": 12,
      "company_id": 1,
      "shop_id": 2,
      "project_id": 3
    }
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication, TokenAuthentication]

    def post(self, request, task_id: int):
        tenant_id = _get_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)
        tenant_id = int(tenant_id)

        if WorkItem is None:
            return Response({"ok": False, "message": "WorkItem not found"}, status=501)

        payload = request.data or {}

        qs = WorkItem.objects_all.all() if hasattr(WorkItem, "objects_all") else WorkItem.objects.all()
        obj = qs.filter(tenant_id=tenant_id, id=int(task_id)).first()
        if not obj:
            return Response({"ok": False, "message": "Task not found"}, status=404)

        fields = ["updated_at"]

        if "title" in payload:
            title = str(payload.get("title") or "").strip()
            if not title:
                return Response({"ok": False, "message": "title không được rỗng"}, status=400)
            obj.title = title
            fields.append("title")

        if "description" in payload:
            obj.description = str(payload.get("description") or "").strip()
            fields.append("description")

        if "priority" in payload:
            pr = _parse_int(payload.get("priority"))
            if pr not in (1, 2, 3, 4):
                return Response({"ok": False, "message": "priority không hợp lệ"}, status=400)
            obj.priority = pr
            fields.append("priority")

        if "status" in payload:
            st = str(payload.get("status") or "").strip().lower()
            if st not in ("todo", "doing", "blocked", "done", "cancelled"):
                return Response({"ok": False, "message": "status không hợp lệ"}, status=400)
            obj.status = st
            fields.append("status")

        if "assignee_id" in payload:
            obj.assignee_id = _parse_int(payload.get("assignee_id"))
            fields.append("assignee_id")

        if "company_id" in payload and hasattr(obj, "company_id"):
            obj.company_id = _parse_int(payload.get("company_id"))
            fields.append("company_id")

        if "shop_id" in payload and hasattr(obj, "shop_id"):
            obj.shop_id = _parse_int(payload.get("shop_id"))
            fields.append("shop_id")

        if "project_id" in payload and hasattr(obj, "project_id"):
            obj.project_id = _parse_int(payload.get("project_id"))
            fields.append("project_id")

        if "due_at" in payload or "deadline" in payload:
            raw_due = payload.get("due_at") if "due_at" in payload else payload.get("deadline")
            if raw_due in ("", None):
                obj.due_at = None
            else:
                dt = _parse_due_at(raw_due)
                if not dt:
                    return Response({"ok": False, "message": "due_at không hợp lệ"}, status=400)
                obj.due_at = dt
            fields.append("due_at")

        # bỏ trùng
        fields = list(dict.fromkeys(fields))

        try:
            obj.save(update_fields=fields)
        except Exception:
            obj.save()

        obj = _reload_item(obj)
        return Response({"ok": True, "item": _serialize_item(obj)})