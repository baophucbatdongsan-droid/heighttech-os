# apps/api/v1/work/views.py
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Optional, Tuple

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.base import TenantRequiredMixin
from apps.api.v1.guards import get_scope_company_ids, get_scope_shop_ids
from apps.core.permissions import (
    AbilityPermission,
    VIEW_API_DASHBOARD,
    resolve_user_role,
    ROLE_FOUNDER,
    ROLE_CLIENT,
)
from apps.projects.models import Project
from apps.work.models import WorkItem, WorkComment
from apps.work.services_move import move_work_item

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
    page_size = _parse_int(request.query_params.get("page_size"), 50)
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
    status_v = (request.query_params.get("status") or "").strip()
    priority_v = (request.query_params.get("priority") or "").strip()
    assignee_v = (request.query_params.get("assignee") or "").strip()
    requester_v = (request.query_params.get("requester") or "").strip()
    company_v = (request.query_params.get("company_id") or "").strip()
    project_v = (request.query_params.get("project_id") or "").strip()
    target_type = (request.query_params.get("target_type") or "").strip()
    target_id = (request.query_params.get("target_id") or "").strip()
    internal_v = (request.query_params.get("is_internal") or "").strip()

    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))

    if status_v:
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


# =========================
# scope
# =========================
def _scope_queryset_for_user(request: Request, qs):
    user = request.user
    tenant_id = getattr(request, "tenant_id", None)

    if tenant_id:
        qs = qs.filter(tenant_id=int(tenant_id))

    role = resolve_user_role(user)
    if role == ROLE_FOUNDER or getattr(user, "is_superuser", False):
        return qs

    if role == ROLE_CLIENT:
        qs = qs.filter(is_internal=False)

    allowed_company_ids = set(get_scope_company_ids(user) or [])
    allowed_shop_ids = set(get_scope_shop_ids(user) or [])

    q_company = Q()
    if allowed_company_ids:
        q_company = Q(company_id__in=list(allowed_company_ids))

    q_client = Q()
    if allowed_shop_ids:
        q_client |= Q(target_type="shop", target_id__in=list(allowed_shop_ids))

        # channel -> shop
        try:
            from apps.channels.models import ChannelShopLink

            channel_ids = set(
                ChannelShopLink.objects_all.filter(shop_id__in=list(allowed_shop_ids))
                .values_list("channel_id", flat=True)
                .distinct()
            )
            if channel_ids:
                q_client |= Q(target_type="channel", target_id__in=list(channel_ids))
        except Exception:
            pass

        # booking -> shop
        try:
            from apps.booking.models import Booking

            booking_ids = set(
                Booking.objects_all.filter(shop_id__in=list(allowed_shop_ids))
                .values_list("id", flat=True)
                .distinct()
            )
            if booking_ids:
                q_client |= Q(target_type="booking", target_id__in=list(booking_ids))
        except Exception:
            pass

    combined = q_company | q_client
    if combined.children:
        return qs.filter(combined)

    return qs.none()


def _validate_write_scope(request: Request, payload: Dict[str, Any]) -> Tuple[bool, str]:
    user = request.user
    role = resolve_user_role(user)

    if role == ROLE_FOUNDER or getattr(user, "is_superuser", False):
        return True, ""

    if role == ROLE_CLIENT:
        return False, "Khách hàng không được thao tác ghi công việc"

    allowed_company_ids = set(get_scope_company_ids(user) or [])
    allowed_shop_ids = set(get_scope_shop_ids(user) or [])

    company_id = payload.get("company_id")
    project_id = payload.get("project_id")
    target_type = (payload.get("target_type") or "").strip()
    target_id = payload.get("target_id")

    if company_id is not None:
        try:
            cid = int(company_id)
            if allowed_company_ids and cid not in allowed_company_ids:
                return False, "Forbidden: company out of scope"
        except Exception:
            return False, "Bad company_id"

    if project_id is not None:
        try:
            pid = int(project_id)
        except Exception:
            return False, "Bad project_id"

        tenant_id = getattr(request, "tenant_id", None)
        p_qs = Project.objects_all.all()
        if tenant_id:
            p_qs = p_qs.filter(tenant_id=int(tenant_id))

        p = p_qs.filter(id=pid).only("id", "company_id").first()
        if not p:
            return False, "Forbidden: project not found in tenant"
        if allowed_company_ids and p.company_id not in allowed_company_ids:
            return False, "Forbidden: project out of company scope"

    if target_id is not None:
        try:
            t_id = int(target_id)
        except Exception:
            return False, "Bad target_id"

        if target_type == "shop":
            if allowed_shop_ids and t_id not in allowed_shop_ids:
                return False, "Forbidden: shop target out of scope"

        elif target_type == "channel":
            try:
                from apps.channels.models import ChannelShopLink

                ok = ChannelShopLink.objects_all.filter(
                    shop_id__in=list(allowed_shop_ids),
                    channel_id=t_id,
                ).exists()
                if allowed_shop_ids and not ok:
                    return False, "Forbidden: channel target out of scope"
            except Exception:
                if allowed_shop_ids:
                    return False, "Forbidden: channel target out of scope"

        elif target_type == "booking":
            try:
                from apps.booking.models import Booking

                ok = Booking.objects_all.filter(id=t_id, shop_id__in=list(allowed_shop_ids)).exists()
                if allowed_shop_ids and not ok:
                    return False, "Forbidden: booking target out of scope"
            except Exception:
                if allowed_shop_ids:
                    return False, "Forbidden: booking target out of scope"

    return True, ""


def _require_company_if_no_resolve_fields(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """
    ✅ FINAL guard (anti-rác):
    Create WorkItem phải có:
      - company_id
      HOẶC
      - project_id
      HOẶC
      - (target_type & target_id)
    """
    company_id = payload.get("company_id")
    project_id = payload.get("project_id")
    target_type = (payload.get("target_type") or "").strip()
    target_id = payload.get("target_id")

    if company_id:
        return True, ""
    if project_id:
        return True, ""
    if target_type and target_id:
        return True, ""
    return False, "company_id là bắt buộc nếu không có project_id hoặc target (target_type/target_id)"


# =========================
# Views
# =========================
class WorkItemListCreateView(generics.GenericAPIView):
    serializer_class = WorkItemSerializer
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def get(self, request: Request, *args, **kwargs):
        qs = _scope_queryset_for_user(request, WorkItem.objects_all.all())
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

        ok_basic, msg_basic = _require_company_if_no_resolve_fields(payload)
        if not ok_basic:
            return Response({"ok": False, "message": msg_basic}, status=status.HTTP_400_BAD_REQUEST)

        ok, msg = _validate_write_scope(request, payload)
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
        qs = _scope_queryset_for_user(request, WorkItem.objects_all.all())
        return get_object_or_404(qs, pk=pk)

    def get(self, request: Request, pk: int, *args, **kwargs):
        obj = self._get_obj(request, pk)
        return Response({"ok": True, "item": WorkItemSerializer(obj, context={"request": request}).data})

    def patch(self, request: Request, pk: int, *args, **kwargs):
        if _is_client(request.user):
            return Response({"ok": False, "message": "Khách hàng không được chỉnh sửa công việc"}, status=status.HTTP_403_FORBIDDEN)

        obj = self._get_obj(request, pk)
        payload = dict(request.data or {})

        # ✅ không cho đổi tenant_id bằng API
        payload.pop("tenant_id", None)

        ok, msg = _validate_write_scope(request, payload)
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
        qs = _scope_queryset_for_user(request, WorkItem.objects_all.all())
        item = get_object_or_404(qs, pk=pk)

        cqs = WorkComment.objects_all.filter(work_item_id=item.id).order_by("-id")[:200]
        data = WorkCommentSerializer(cqs, many=True).data
        return Response({"ok": True, "work_item_id": item.id, "items": data})


class WorkItemAddCommentView(generics.GenericAPIView):
    """
    Client được phép comment (trên task public).
    """
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD
    serializer_class = WorkCommentCreateSerializer

    def post(self, request: Request, pk: int, *args, **kwargs):
        qs = _scope_queryset_for_user(request, WorkItem.objects_all.all())
        item = get_object_or_404(qs, pk=pk)

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
        base = _scope_queryset_for_user(request, WorkItem.objects_all.all())

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
                        my_assigned.order_by("-updated_at", "-id")[:20],
                        many=True,
                        context={"request": request},
                    ).data,
                    "requested_items": WorkItemSerializer(
                        my_requested.order_by("-updated_at", "-id")[:20],
                        many=True,
                        context={"request": request},
                    ).data,
                },
                "due_soon": WorkItemSerializer(due_soon, many=True, context={"request": request}).data,
                "recent_timeline": WorkCommentSerializer(comment_qs, many=True).data,
            }
        )


class WorkPortalSummaryView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def get(self, request: Request, *args, **kwargs):
        base = _scope_queryset_for_user(request, WorkItem.objects_all.all())

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
                "recent_items": WorkItemSerializer(recent_items, many=True, context={"request": request}).data,
                "due_soon": WorkItemSerializer(due_soon, many=True, context={"request": request}).data,
                "recent_timeline": WorkCommentSerializer(cqs, many=True).data,
            }
        )


class WorkBoardView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def get(self, request: Request, *args, **kwargs):
        qs = _scope_queryset_for_user(request, WorkItem.objects_all.all())

        scope = (request.query_params.get("scope") or "all").strip().lower()

        if scope == "shop":
            shop_id = request.query_params.get("shop_id")
            if shop_id:
                try:
                    qs = qs.filter(target_type="shop", target_id=int(shop_id))
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
            {
                "ok": True,
                "scope": scope,
                "limit": limit,
                "sort": sort,
                "dir": direction,
                "totals": totals,
                "columns": columns,
            }
        )


class WorkItemMoveView(TenantRequiredMixin, APIView):
    """
    POST /api/v1/work/items/<pk>/move/
    body:
      {
        "to_status": "doing",
        "to_position": 2
      }
    """
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

        base = _scope_queryset_for_user(request, WorkItem.objects_all.all())
        item = get_object_or_404(base, pk=pk, tenant_id=tenant.id)

        try:
            res = move_work_item(
                tenant_id=tenant.id,
                item_id=int(item.id),
                to_status=to_status,
                to_position=int(to_position) if to_position is not None else None,
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