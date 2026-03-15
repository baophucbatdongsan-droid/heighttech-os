# apps/api/v1/work/views.py
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, status, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.base import TenantRequiredMixin
from apps.core.permissions import (
    AbilityPermission,
    VIEW_API_DASHBOARD,
    resolve_user_role,
    ROLE_CLIENT,
)
from apps.work.models import WorkItem
from apps.work.models_comment import WorkComment
from apps.work.services_move import move_work_item
from apps.work.permissions import (
    scope_workitem_queryset,
    validate_write_scope,
    require_company_if_no_resolve_fields,
    get_scoped_workitem_or_404,
)

from .serializers import (
    WorkItemSerializer,
    WorkCommentSerializer,
    WorkCommentCreateSerializer,
    WorkItemMoveSerializer,
)

MAX_PAGE_SIZE = 200
STATUSES = ["todo", "doing", "blocked", "done", "cancelled"]


# =========================
# helpers
# =========================
def _parse_int(s: Optional[str], default: int) -> int:
    try:
        return int((s or "").strip())
    except Exception:
        return default


def _paginate(request: Request, qs):
    page = max(_parse_int(request.query_params.get("page"), 1), 1)

    raw_page_size = (
        request.query_params.get("page_size")
        or request.query_params.get("limit")
        or "50"
    )
    page_size = _parse_int(raw_page_size, 50)

    if page_size <= 0:
        page_size = 50
    page_size = min(page_size, MAX_PAGE_SIZE)

    total = qs.count()
    start = (page - 1) * page_size
    end = start + page_size
    return page, page_size, total, qs[start:end]


def _safe_sort(sort: str) -> str:
    allowed = {"id", "created_at", "updated_at", "due_at", "done_at", "priority", "status", "position"}
    s = (sort or "").strip()
    return s if s in allowed else "updated_at"


def _apply_filters(request: Request, qs):
    q = (request.query_params.get("q") or "").strip()
    status_v = (request.query_params.get("status") or "").strip().lower()
    priority_v = (request.query_params.get("priority") or "").strip()
    assignee_v = (request.query_params.get("assignee") or "").strip()
    requester_v = (request.query_params.get("requester") or "").strip()
    company_v = (request.query_params.get("company_id") or "").strip()
    shop_v = (request.query_params.get("shop_id") or "").strip()
    project_v = (request.query_params.get("project_id") or "").strip()
    target_type = (request.query_params.get("target_type") or "").strip()
    target_id = (request.query_params.get("target_id") or "").strip()
    internal_v = (request.query_params.get("is_internal") or "").strip()

    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))

    if status_v:
        if status_v == "open":
            qs = qs.exclude(status__in=["done", "cancelled"])
        else:
            qs = qs.filter(status=status_v)

    if priority_v:
        try:
            qs = qs.filter(priority=int(priority_v))
        except Exception:
            pass

    if assignee_v:
        try:
            qs = qs.filter(assignee_id=int(assignee_v))
        except Exception:
            pass

    if requester_v:
        try:
            qs = qs.filter(requester_id=int(requester_v))
        except Exception:
            pass

    if company_v:
        try:
            qs = qs.filter(company_id=int(company_v))
        except Exception:
            pass

    if shop_v:
        try:
            qs = qs.filter(shop_id=int(shop_v))
        except Exception:
            pass

    if project_v:
        try:
            qs = qs.filter(project_id=int(project_v))
        except Exception:
            pass

    if target_type:
        qs = qs.filter(target_type=target_type)

    if target_id:
        try:
            qs = qs.filter(target_id=int(target_id))
        except Exception:
            pass

    if internal_v:
        v = internal_v.lower() in {"1", "true", "yes"}
        qs = qs.filter(is_internal=bool(v))

    return qs


def _is_client(user) -> bool:
    return resolve_user_role(user) == ROLE_CLIENT


def _apply_client_scope(request: Request, qs):
    if _is_client(request.user):
        qs = qs.filter(visible_to_client=True, is_internal=False)
    return qs


def _with_related(qs):
    return qs.select_related(
        "assignee",
        "requester",
        "created_by",
        "project",
        "shop",
    )


def _client_forbidden_item(item: WorkItem) -> bool:
    return (not bool(getattr(item, "visible_to_client", False))) or bool(getattr(item, "is_internal", False))


# =========================
# Views
# =========================
class WorkItemListCreateView(generics.GenericAPIView):
    serializer_class = WorkItemSerializer
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def get(self, request: Request, *args, **kwargs):
        qs = scope_workitem_queryset(request, WorkItem.objects_all.all())
        qs = _with_related(qs)
        qs = _apply_client_scope(request, qs)
        qs = _apply_filters(request, qs)

        sort = _safe_sort(request.query_params.get("sort") or "updated_at")
        direction = (request.query_params.get("dir") or "desc").lower().strip()
        order_by = f"-{sort}" if direction != "asc" else sort
        qs = qs.order_by(order_by, "-id")

        page, page_size, total, sliced = _paginate(request, qs)
        data = WorkItemSerializer(sliced, many=True, context={"request": request}).data
        return Response({"ok": True, "total": total, "page": page, "page_size": page_size, "items": data})

    def post(self, request: Request, *args, **kwargs):
        if _is_client(request.user):
            return Response({"ok": False, "message": "Khách hàng không được tạo công việc"}, status=status.HTTP_403_FORBIDDEN)

        payload = dict(request.data or {})

        ok_basic, msg_basic = require_company_if_no_resolve_fields(payload)
        if not ok_basic:
            return Response({"ok": False, "message": msg_basic}, status=status.HTTP_400_BAD_REQUEST)

        ok, msg = validate_write_scope(request, payload)
        if not ok:
            return Response({"ok": False, "message": msg}, status=status.HTTP_403_FORBIDDEN)

        ser = WorkItemSerializer(data=payload, context={"request": request})
        ser.is_valid(raise_exception=True)

        tenant_id = getattr(request, "tenant_id", None)
        obj = WorkItem(**ser.validated_data)
        if tenant_id:
            obj.tenant_id = int(tenant_id)

        obj.created_by = request.user
        obj._actor = request.user  # type: ignore[attr-defined]
        obj.save()

        return Response(
            {"ok": True, "item": WorkItemSerializer(obj, context={"request": request}).data},
            status=status.HTTP_201_CREATED,
        )


class WorkItemDetailView(generics.GenericAPIView):
    serializer_class = WorkItemSerializer
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def _get_obj(self, request: Request, pk: int) -> WorkItem:
        return get_scoped_workitem_or_404(request, pk)

    def get(self, request: Request, pk: int, *args, **kwargs):
        obj = self._get_obj(request, pk)
        if _is_client(request.user) and _client_forbidden_item(obj):
            return Response({"ok": False, "message": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        return Response({"ok": True, "item": WorkItemSerializer(obj, context={"request": request}).data})

    def patch(self, request: Request, pk: int, *args, **kwargs):
        if _is_client(request.user):
            return Response({"ok": False, "message": "Khách hàng không được chỉnh sửa công việc"}, status=status.HTTP_403_FORBIDDEN)

        obj = self._get_obj(request, pk)
        payload = dict(request.data or {})
        payload.pop("tenant_id", None)

        ok, msg = validate_write_scope(request, payload)
        if not ok:
            return Response({"ok": False, "message": msg}, status=status.HTTP_403_FORBIDDEN)

        ser = WorkItemSerializer(obj, data=payload, partial=True, context={"request": request})
        ser.is_valid(raise_exception=True)

        for k, v in ser.validated_data.items():
            setattr(obj, k, v)

        obj._actor = request.user  # type: ignore[attr-defined]
        obj.save()

        return Response({"ok": True, "item": WorkItemSerializer(obj, context={"request": request}).data})

    def delete(self, request: Request, pk: int, *args, **kwargs):
        if _is_client(request.user):
            return Response({"ok": False, "message": "Khách hàng không được xoá công việc"}, status=status.HTTP_403_FORBIDDEN)

        obj = self._get_obj(request, pk)
        obj._actor = request.user  # type: ignore[attr-defined]
        obj.delete()
        return Response({"ok": True})


class WorkItemTimelineView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def get(self, request: Request, pk: int, *args, **kwargs):
        item = get_scoped_workitem_or_404(request, pk)
        if _is_client(request.user) and _client_forbidden_item(item):
            return Response({"ok": False, "message": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        cqs = WorkComment.objects_all.filter(work_item_id=item.id).order_by("-id")[:200]
        data = WorkCommentSerializer(cqs, many=True).data
        return Response({"ok": True, "work_item_id": item.id, "items": data})


class WorkItemAddCommentView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD
    serializer_class = WorkCommentCreateSerializer

    def post(self, request: Request, pk: int, *args, **kwargs):
        item = get_scoped_workitem_or_404(request, pk)
        if _is_client(request.user) and _client_forbidden_item(item):
            return Response({"ok": False, "message": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        ser = self.get_serializer(data=request.data or {})
        ser.is_valid(raise_exception=True)

        tenant_id = getattr(request, "tenant_id", None)
        c = WorkComment.objects_all.create(
            tenant_id=int(tenant_id) if tenant_id else item.tenant_id,
            work_item_id=item.id,
            actor_id=request.user.id,
            body=ser.validated_data["body"],
            meta={"event": "comment", **(ser.validated_data.get("meta") or {})},
        )

        try:
            item._actor = request.user  # type: ignore[attr-defined]
            item.save()
        except Exception:
            pass

        return Response({"ok": True, "comment": WorkCommentSerializer(c).data}, status=status.HTTP_201_CREATED)


class WorkMySummaryView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def get(self, request: Request, *args, **kwargs):
        user = request.user
        base = scope_workitem_queryset(request, WorkItem.objects_all.all())
        base = _apply_client_scope(request, base)

        def _count(st: str) -> int:
            return base.filter(status=st).count()

        counts = {st: _count(st) for st in STATUSES}
        counts["total"] = base.count()

        my_assigned = base.filter(assignee_id=user.id).exclude(status__in=["done", "cancelled"])
        my_requested = base.filter(requester_id=user.id).exclude(status__in=["done", "cancelled"])

        now = timezone.now()
        soon = now + timedelta(days=7)
        due_soon = (
            base.filter(due_at__isnull=False, due_at__lte=soon)
            .exclude(status__in=["done", "cancelled"])
            .order_by("due_at", "-priority")[:20]
        )

        scoped_ids = list(base.values_list("id", flat=True)[:2000])
        comment_qs = (
            WorkComment.objects_all.filter(work_item_id__in=scoped_ids).order_by("-id")[:50]
            if scoped_ids
            else WorkComment.objects_all.none()
        )

        return Response(
            {
                "ok": True,
                "counts": counts,
                "my": {
                    "assigned_total": my_assigned.count(),
                    "requested_total": my_requested.count(),
                    "assigned_items": WorkItemSerializer(
                        _with_related(my_assigned.order_by("-updated_at", "-id")[:20]),
                        many=True,
                        context={"request": request},
                    ).data,
                    "requested_items": WorkItemSerializer(
                        _with_related(my_requested.order_by("-updated_at", "-id")[:20]),
                        many=True,
                        context={"request": request},
                    ).data,
                },
                "due_soon": WorkItemSerializer(_with_related(due_soon), many=True, context={"request": request}).data,
                "recent_timeline": WorkCommentSerializer(comment_qs, many=True).data,
            }
        )


class WorkPortalSummaryView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def get(self, request: Request, *args, **kwargs):
        base = scope_workitem_queryset(request, WorkItem.objects_all.all())
        base = _apply_client_scope(request, base)

        counts = {st: base.filter(status=st).count() for st in STATUSES}
        counts["total"] = base.count()

        now = timezone.now()
        soon = now + timedelta(days=7)
        due_soon = (
            base.filter(due_at__isnull=False, due_at__lte=soon)
            .exclude(status__in=["done", "cancelled"])
            .order_by("due_at", "-priority")[:20]
        )

        scoped_ids = list(base.values_list("id", flat=True)[:2000])
        cqs = (
            WorkComment.objects_all.filter(work_item_id__in=scoped_ids).order_by("-id")[:30]
            if scoped_ids
            else WorkComment.objects_all.none()
        )

        recent_items = base.order_by("-updated_at", "-id")[:20]

        return Response(
            {
                "ok": True,
                "role": resolve_user_role(request.user),
                "counts": counts,
                "recent_items": WorkItemSerializer(_with_related(recent_items), many=True, context={"request": request}).data,
                "due_soon": WorkItemSerializer(_with_related(due_soon), many=True, context={"request": request}).data,
                "recent_timeline": WorkCommentSerializer(cqs, many=True).data,
            }
        )


class WorkBoardView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def get(self, request: Request, *args, **kwargs):
        qs = scope_workitem_queryset(request, WorkItem.objects_all.all())
        qs = _with_related(qs)
        qs = _apply_client_scope(request, qs)

        scope = (request.query_params.get("scope") or "all").strip().lower()

        if scope == "shop":
            shop_id = request.query_params.get("shop_id")
            if shop_id:
                try:
                    qs = qs.filter(shop_id=int(shop_id))
                except Exception:
                    return Response({"ok": False, "message": "Bad shop_id"}, status=400)

        elif scope == "company":
            company_id = request.query_params.get("company_id")
            if company_id:
                try:
                    qs = qs.filter(company_id=int(company_id))
                except Exception:
                    return Response({"ok": False, "message": "Bad company_id"}, status=400)

        elif scope == "project":
            project_id = request.query_params.get("project_id")
            if project_id:
                try:
                    qs = qs.filter(project_id=int(project_id))
                except Exception:
                    return Response({"ok": False, "message": "Bad project_id"}, status=400)

        elif scope == "target":
            target_type = (request.query_params.get("target_type") or "").strip()
            target_id = request.query_params.get("target_id")
            if not target_type or not target_id:
                return Response(
                    {"ok": False, "message": "target_type and target_id are required for scope=target"},
                    status=400,
                )
            try:
                qs = qs.filter(target_type=target_type, target_id=int(target_id))
            except Exception:
                return Response({"ok": False, "message": "Bad target_id"}, status=400)

        elif scope == "all":
            pass
        else:
            return Response({"ok": False, "message": "Bad scope"}, status=400)

        qs = _apply_filters(request, qs)

        sort = _safe_sort(request.query_params.get("sort") or "updated_at")
        direction = (request.query_params.get("dir") or "desc").lower().strip()
        _ = sort, direction

        limit = _parse_int(request.query_params.get("limit"), 50)
        if limit <= 0:
            limit = 50
        limit = min(limit, MAX_PAGE_SIZE)

        columns = []
        totals = {}

        for st in STATUSES:
            col_qs = qs.filter(status=st).order_by("position", "id")
            total = col_qs.count()
            items = WorkItemSerializer(col_qs[:limit], many=True, context={"request": request}).data
            columns.append({"status": st, "total": total, "items": items})
            totals[st] = total

        return Response(
            {"ok": True, "scope": scope, "limit": limit, "sort": sort, "dir": direction, "totals": totals, "columns": columns}
        )


class WorkItemMoveView(TenantRequiredMixin, APIView):
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def post(self, request, pk: int):
        if _is_client(request.user):
            return Response(
                {"ok": False, "detail": "Khách hàng không được thay đổi trạng thái"},
                status=status.HTTP_403_FORBIDDEN,
            )

        tenant = self.get_tenant()

        ser = WorkItemMoveSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        to_status = (ser.validated_data.get("to_status") or "").strip()
        to_position = ser.validated_data.get("to_position", None)

        if not to_status:
            return Response({"ok": False, "detail": "to_status is required"}, status=status.HTTP_400_BAD_REQUEST)

        item = get_scoped_workitem_or_404(request, pk)
        if int(item.tenant_id) != int(tenant.id):
            return Response({"ok": False, "detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        try:
            res = move_work_item(
                tenant_id=tenant.id,
                item_id=int(item.id),
                to_status=to_status,
                to_position=int(to_position) if to_position is not None else None,
                actor_id=getattr(request.user, "id", None),
            )
        except ValueError as e:
            return Response({"ok": False, "detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        item.refresh_from_db()
        return Response(
            {
                "ok": True,
                "moved": {
                    "from_status": res.from_status,
                    "to_status": res.to_status,
                    "from_position": res.from_position,
                    "to_position": res.to_position,
                },
                "item": WorkItemSerializer(item, context={"request": request}).data,
            }
        )


# =========================
# ✅ NEW: Assign
# =========================
class WorkItemAssignSerializer(serializers.Serializer):
    assignee_id = serializers.IntegerField(required=False, allow_null=True)
    requester_id = serializers.IntegerField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        if "assignee_id" not in attrs and "requester_id" not in attrs:
            raise serializers.ValidationError("assignee_id hoặc requester_id là bắt buộc")
        return attrs


class WorkItemAssignView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD
    serializer_class = WorkItemAssignSerializer

    def post(self, request: Request, pk: int, *args, **kwargs):
        if _is_client(request.user):
            return Response({"ok": False, "message": "Khách hàng không được phân công"}, status=status.HTTP_403_FORBIDDEN)

        item = get_scoped_workitem_or_404(request, pk)

        payload = dict(request.data or {})
        ok, msg = validate_write_scope(request, payload)
        if not ok:
            return Response({"ok": False, "message": msg}, status=status.HTTP_403_FORBIDDEN)

        ser = self.get_serializer(data=payload)
        ser.is_valid(raise_exception=True)

        assignee_id = ser.validated_data.get("assignee_id", None)
        requester_id = ser.validated_data.get("requester_id", None)
        note = (ser.validated_data.get("note") or "").strip()

        with transaction.atomic():
            updated = set()

            if "assignee_id" in ser.validated_data:
                item.assignee_id = assignee_id
                updated.add("assignee_id")

            if "requester_id" in ser.validated_data:
                item.requester_id = requester_id
                updated.add("requester_id")

            item._actor = request.user  # type: ignore[attr-defined]
            if updated:
                item.save(update_fields=list(updated) + ["updated_at"])
            else:
                item.save()

            if note or updated:
                WorkComment.objects_all.create(
                    tenant_id=item.tenant_id,
                    work_item_id=item.id,
                    actor_id=request.user.id,
                    body=note or "Updated assignment",
                    meta={
                        "event": "assign",
                        "assignee_id": item.assignee_id,
                        "requester_id": item.requester_id,
                    },
                )

        item.refresh_from_db()
        return Response({"ok": True, "item": WorkItemSerializer(item, context={"request": request}).data})