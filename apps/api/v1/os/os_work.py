#apps/api/v1/os/os_work.py

from __future__ import annotations

from typing import Any, Dict, Optional

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.insight import _get_tenant_id
from apps.events.bus import emit_event, make_dedupe_key
from apps.work.models_comment import WorkComment
from apps.work.services_move import create_work_item, move_work_item
from django.core.exceptions import ValidationError


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


def _require_tenant_id(request) -> Optional[int]:
    tid = _get_tenant_id(request)
    try:
        return int(tid) if tid else None
    except Exception:
        return None


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


def _serialize_comment(x):
    actor = getattr(x, "actor", None)

    actor_name = ""
    if actor:
        actor_name = (
            getattr(actor, "full_name", "")
            or getattr(actor, "get_full_name", lambda: "")()
            or getattr(actor, "username", "")
            or getattr(actor, "email", "")
        )

    return {
        "id": x.id,
        "body": x.body or "",
        "meta": x.meta or {},
        "actor_id": x.actor_id,
        "actor_name": actor_name,
        "actor_email": getattr(actor, "email", "") if actor else "",
        "created_at": x.created_at.isoformat() if x.created_at else None,
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

    def get(self, request, *args, **kwargs):
        tenant_id = _require_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        page = int(request.GET.get("page", 1) or 1)
        page_size = int(request.GET.get("page_size", 200) or 200)
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 200

        company_id = _parse_int(request.GET.get("company_id"))
        shop_id = _parse_int(request.GET.get("shop_id"))
        project_id = _parse_int(request.GET.get("project_id"))
        status = (request.GET.get("status") or request.GET.get("view") or "board").strip().lower()

        qs = (
            WorkItem.objects_all
            .filter(tenant_id=tenant_id)
            .select_related("assignee", "requester", "project", "shop", "company")
            .order_by("status", "rank", "id")
        )

        if company_id:
            qs = qs.filter(company_id=company_id)
        if shop_id:
            qs = qs.filter(shop_id=shop_id)
        if project_id:
            qs = qs.filter(project_id=project_id)

        filtered_qs, _ = _apply_open_filter(qs, status)

        total = filtered_qs.count()
        open_count = qs.exclude(status__in=["done", "cancelled"]).count()

        start = (page - 1) * page_size
        end = start + page_size
        rows = list(filtered_qs[start:end])

        items = [_serialize_item(x) for x in rows]

        return Response({
            "ok": True,
            "tenant_id": tenant_id,
            "total": total,
            "page": page,
            "page_size": page_size,
            "open_count": open_count,
            "items": items,
        })


class OSWorkCreateApi(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication, TokenAuthentication]

    def post(self, request):
        tenant_id = _require_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

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
        tenant_id = _require_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        if WorkItem is None:
            return Response({"ok": False, "message": "WorkItem not found"}, status=501)

        assignee_id = _parse_int((request.data or {}).get("assignee_id"))
        if not assignee_id:
            return Response({"ok": False, "message": "assignee_id không hợp lệ"}, status=400)

        qs = WorkItem.objects_all.all() if hasattr(WorkItem, "objects_all") else WorkItem.objects.all()
        obj = qs.filter(tenant_id=tenant_id, id=int(task_id)).first()
        if not obj:
            return Response({"ok": False, "message": "Task not found"}, status=404)

        old_assignee_id = getattr(obj, "assignee_id", None)
        obj.assignee_id = int(assignee_id)

        try:
            obj.save(update_fields=["assignee_id", "updated_at"])
        except Exception:
            obj.save()

        if int(assignee_id) != int(old_assignee_id or 0):
            try:
                payload = {
                    "id": obj.id,
                    "work_item_id": obj.id,
                    "title": getattr(obj, "title", ""),
                    "status": getattr(obj, "status", ""),
                    "assignee_id": obj.assignee_id,
                    "old_assignee_id": old_assignee_id,
                }

                dedupe = make_dedupe_key(
                    name="work.item.assigned",
                    tenant_id=tenant_id,
                    entity="workitem",
                    entity_id=obj.id,
                    extra={
                        "assignee_id": str(obj.assignee_id or ""),
                        "updated_at": obj.updated_at.isoformat() if getattr(obj, "updated_at", None) else "",
                    },
                )

                transaction.on_commit(
                    lambda: emit_event(
                        tenant_id=tenant_id,
                        company_id=getattr(obj, "company_id", None),
                        shop_id=getattr(obj, "shop_id", None),
                        actor_id=getattr(request.user, "id", None),
                        name="work.item.assigned",
                        version=1,
                        dedupe_key=dedupe,
                        payload=payload,
                    )
                )
            except Exception:
                pass

        obj = _reload_item(obj)
        return Response({"ok": True, "item": _serialize_item(obj)})


class OSWorkMoveApi(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication, TokenAuthentication]

    def post(self, request, task_id: int, *args, **kwargs):
        tenant_id = _require_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        if WorkItem is None:
            return Response({"ok": False, "message": "WorkItem not found"}, status=501)

        to_status = (request.data.get("to_status") or request.data.get("status") or "").strip().lower()
        to_position = request.data.get("to_position")

        if not to_status:
            return Response({"ok": False, "message": "to_status is required"}, status=400)

        try:
            to_position = int(to_position) if to_position is not None else None
        except Exception:
            return Response({"ok": False, "message": "to_position không hợp lệ"}, status=400)

        qs = WorkItem.objects_all.select_related("assignee", "requester", "project", "shop", "company")
        obj = qs.filter(id=int(task_id), tenant_id=tenant_id).first()
        if not obj:
            return Response({"ok": False, "message": "Task not found"}, status=404)

        try:
            res = move_work_item(
                tenant_id=tenant_id,
                item_id=int(task_id),
                to_status=to_status,
                to_position=to_position,
                actor_id=getattr(request.user, "id", None),
            )
        except ValidationError as e:
            return Response({"ok": False, "message": str(e)}, status=400)
        except ValueError as e:
            return Response({"ok": False, "message": str(e)}, status=404)
        except Exception as e:
            return Response({"ok": False, "message": str(e)}, status=400)

        try:
            fresh = (
                WorkItem.objects_all
                .select_related("assignee", "requester", "project", "shop", "company")
                .get(id=task_id, tenant_id=tenant_id)
            )
        except WorkItem.DoesNotExist:
            return Response({"ok": False, "message": "Task không tồn tại sau khi move"}, status=404)

        moved = {
            "from_status": res.from_status,
            "to_status": res.to_status,
            "from_position": res.from_position,
            "to_position": res.to_position,
        }

        return Response({
            "ok": True,
            "moved": moved,
            "item": _serialize_item(fresh),
        })


class OSWorkUpdateApi(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication, TokenAuthentication]

    def post(self, request, task_id: int):
        tenant_id = _require_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        if WorkItem is None:
            return Response({"ok": False, "message": "WorkItem not found"}, status=501)

        payload = request.data or {}

        qs = WorkItem.objects_all.all() if hasattr(WorkItem, "objects_all") else WorkItem.objects.all()
        obj = qs.filter(tenant_id=tenant_id, id=int(task_id)).first()
        if not obj:
            return Response({"ok": False, "message": "Task not found"}, status=404)

        changed_fields = []

        if "title" in payload:
            title = str(payload.get("title") or "").strip()
            if not title:
                return Response({"ok": False, "message": "title không được rỗng"}, status=400)
            obj.title = title
            changed_fields.append("title")

        if "description" in payload:
            obj.description = str(payload.get("description") or "").strip()
            changed_fields.append("description")

        if "priority" in payload:
            pr = _parse_int(payload.get("priority"))
            if pr not in (1, 2, 3, 4):
                return Response({"ok": False, "message": "priority không hợp lệ"}, status=400)
            obj.priority = pr
            changed_fields.append("priority")

        if "status" in payload:
            st = str(payload.get("status") or "").strip().lower()
            if st not in ("todo", "doing", "blocked", "done", "cancelled"):
                return Response({"ok": False, "message": "status không hợp lệ"}, status=400)
            obj.status = st
            changed_fields.append("status")

        if "assignee_id" in payload:
            obj.assignee_id = _parse_int(payload.get("assignee_id"))
            changed_fields.append("assignee_id")

        if "company_id" in payload and hasattr(obj, "company_id"):
            obj.company_id = _parse_int(payload.get("company_id"))
            changed_fields.append("company_id")

        if "shop_id" in payload and hasattr(obj, "shop_id"):
            obj.shop_id = _parse_int(payload.get("shop_id"))
            changed_fields.append("shop_id")

        if "project_id" in payload and hasattr(obj, "project_id"):
            obj.project_id = _parse_int(payload.get("project_id"))
            changed_fields.append("project_id")

        if "due_at" in payload or "deadline" in payload:
            raw_due = payload.get("due_at") if "due_at" in payload else payload.get("deadline")
            if raw_due in ("", None):
                obj.due_at = None
            else:
                dt = _parse_due_at(raw_due)
                if not dt:
                    return Response({"ok": False, "message": "due_at không hợp lệ"}, status=400)
                obj.due_at = dt
            changed_fields.append("due_at")

        try:
            if changed_fields:
                obj.save(update_fields=list(dict.fromkeys(changed_fields + ["updated_at"])))
            else:
                obj.save()
        except Exception:
            obj.save()

        obj = _reload_item(obj)
        return Response({"ok": True, "item": _serialize_item(obj)})


class OSWorkCommentsApi(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication, TokenAuthentication]

    def get(self, request, task_id: int, *args, **kwargs):
        tenant_id = _require_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        qs = (
            WorkComment.objects_all
            .filter(tenant_id=tenant_id, work_item_id=task_id)
            .select_related("actor")
            .order_by("created_at", "id")
        )

        items = [_serialize_comment(x) for x in qs]
        return Response({"ok": True, "items": items})

    def post(self, request, task_id: int, *args, **kwargs):
        tenant_id = _require_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        body = (request.data.get("body") or request.data.get("content") or "").strip()
        if not body:
            return Response({"ok": False, "message": "body is required"}, status=400)

        task = WorkItem.objects_all.filter(id=task_id, tenant_id=tenant_id).first()
        if not task:
            return Response({"ok": False, "message": "Task not found"}, status=404)

        comment = WorkComment.objects_all.create(
            tenant_id=tenant_id,
            work_item_id=task_id,
            actor=request.user if getattr(request.user, "is_authenticated", False) else None,
            body=body,
            meta={},
        )

        comment = (
            WorkComment.objects_all
            .select_related("actor")
            .get(id=comment.id)
        )

        try:
            payload = {
                "id": task.id,
                "work_item_id": task.id,
                "comment_id": comment.id,
                "body": comment.body,
                "actor_id": getattr(comment, "actor_id", None),
                "title": getattr(task, "title", ""),
                "status": getattr(task, "status", ""),
            }

            dedupe = make_dedupe_key(
                name="work.item.commented",
                tenant_id=tenant_id,
                entity="workcomment",
                entity_id=comment.id,
                extra={"work_item_id": task.id},
            )

            transaction.on_commit(
                lambda: emit_event(
                    tenant_id=tenant_id,
                    company_id=getattr(task, "company_id", None),
                    shop_id=getattr(task, "shop_id", None),
                    actor_id=getattr(comment, "actor_id", None),
                    name="work.item.commented",
                    version=1,
                    dedupe_key=dedupe,
                    payload=payload,
                )
            )
        except Exception:
            pass

        return Response({"ok": True, "item": _serialize_comment(comment)}, status=201)


class OSWorkQuickCreateApi(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication, TokenAuthentication]

    def post(self, request, *args, **kwargs):
        tenant_id = _require_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        text = (request.data.get("text") or "").strip()
        status = (request.data.get("status") or "todo").strip().lower()

        if not text:
            return Response({"ok": False, "message": "text is required"}, status=400)

        lines = [x.strip() for x in text.split("\n") if x.strip()]
        created = []

        for title in lines:
            item = create_work_item(
                tenant_id=tenant_id,
                company_id=None,
                title=title,
                status=status,
                created_by_id=request.user.id,
                requester_id=request.user.id,
            )

            created.append({
                "id": item.id,
                "title": item.title,
                "status": item.status,
                "rank": item.rank,
            })

        return Response({
            "ok": True,
            "tenant_id": tenant_id,
            "count": len(created),
            "items": created,
        })