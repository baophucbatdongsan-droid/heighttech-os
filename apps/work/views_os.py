# FILE: apps/work/views_os.py
from __future__ import annotations

import json
from datetime import timedelta
from typing import Any, Dict, Optional

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.core.decorators import require_ability
from apps.core.policy import VIEW_DASHBOARD
from apps.shops.models import ShopMember
from apps.work.models import WorkItem
from apps.work.models_comment import WorkComment
from apps.work.services.workitem_engine import transition_workitem
from apps.work.services_move import create_work_item
User = get_user_model()


# -----------------------------
# Request helpers (OS-grade)
# -----------------------------
def _is_ajax(request: HttpRequest) -> bool:
    return (request.headers.get("x-requested-with") or "").lower() == "xmlhttprequest"


def _is_json(request: HttpRequest) -> bool:
    ct = (request.headers.get("content-type") or "").lower()
    return "application/json" in ct


def _read_json(request: HttpRequest) -> Dict[str, Any]:
    try:
        body = request.body.decode("utf-8") if request.body else ""
        return json.loads(body) if body else {}
    except Exception:
        return {}


def _pick_str(payload, key: str) -> str:
    try:
        v = payload.get(key, "")
        return (str(v) if v is not None else "").strip()
    except Exception:
        return ""


def _can_use_actor(user) -> bool:
    return bool(getattr(user, "is_authenticated", False) and getattr(user, "pk", None))


def _status_label(st: str) -> str:
    st = (st or "").strip().lower()
    return {
        "todo": "TODO",
        "doing": "DOING",
        "blocked": "BLOCKED",
        "done": "DONE",
        "cancelled": "CANCELLED",
    }.get(st, st.upper() or "UNKNOWN")


def _tenant_id(request: HttpRequest) -> Optional[int]:
    # 1) middleware set
    tid = getattr(request, "tenant_id", None)
    try:
        if tid:
            return int(tid)
    except Exception:
        pass

    # 2) session fallback
    for k in ("tenant_id", "active_tenant_id", "current_tenant_id"):
        try:
            v = request.session.get(k)
            if v:
                return int(v)
        except Exception:
            pass

    # 3) actor context fallback
    try:
        actor = getattr(request, "actor", None)
        if actor and getattr(actor, "tenant_id", None):
            return int(actor.tenant_id)
    except Exception:
        pass

    return None


def _users_in_tenant(tid: int, *, shop_id: Optional[int] = None):
    """
    OS-grade:
    - Nếu item có shop_id: list members của shop đó
    - Nếu chưa có shop_id: list all users có ShopMember trong tenant (distinct)
    """
    m = ShopMember.objects_all.filter(tenant_id=tid, is_active=True)
    if shop_id:
        m = m.filter(shop_id=shop_id)

    user_ids = list(m.values_list("user_id", flat=True).distinct())
    if not user_ids:
        return []

    return list(User.objects.filter(id__in=user_ids, is_active=True).only("id", "username").order_by("username"))


def _user_belongs_to_tenant(tid: int, user_id: int, *, shop_id: Optional[int] = None) -> bool:
    qs = ShopMember.objects_all.filter(tenant_id=tid, is_active=True, user_id=user_id)
    if shop_id:
        qs = qs.filter(shop_id=shop_id)
    return qs.exists()


# -----------------------------
# Views
# -----------------------------
@login_required
@require_ability(VIEW_DASHBOARD)
def os_home(request: HttpRequest):
    tid = _tenant_id(request)
    if not tid:
        return redirect("/dashboard/")

    qs = WorkItem.objects.filter(tenant_id=tid)

    # ✅ optional: filter theo shop (phase 2)
    shop_id = (request.GET.get("shop") or "").strip()
    if shop_id:
        try:
            qs = qs.filter(shop_id=int(shop_id))
        except Exception:
            pass

    # filters
    q = (request.GET.get("q") or "").strip()
    st = (request.GET.get("status") or "").strip().lower()
    pr = (request.GET.get("priority") or "").strip()

    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
    if st:
        qs = qs.filter(status=st)
    if pr:
        try:
            qs = qs.filter(priority=int(pr))
        except Exception:
            pass

    now = timezone.now()
    last_7d = now - timedelta(days=7)

    total = qs.exclude(status=WorkItem.Status.CANCELLED).count()
    overdue = qs.filter(due_at__isnull=False, due_at__lt=now).exclude(
        status__in=[WorkItem.Status.DONE, WorkItem.Status.CANCELLED]
    ).count()
    urgent = qs.filter(priority=WorkItem.Priority.URGENT).exclude(
        status__in=[WorkItem.Status.DONE, WorkItem.Status.CANCELLED]
    ).count()
    done_7d = qs.filter(status=WorkItem.Status.DONE, done_at__gte=last_7d).count()

    status_counts_qs = qs.values("status").annotate(c=Count("id"))
    status_counts = {r["status"]: r["c"] for r in status_counts_qs}

    def col(status: str, limit: int = 120):
        return list(
            qs.filter(status=status)
            .select_related("assignee", "requester", "project", "company", "shop")
            .only(
                "id",
                "title",
                "status",
                "priority",
                "due_at",
                "position",
                "rank",
                "assignee_id",
                "requester_id",
                "project_id",
                "company_id",
                "shop_id",
                "updated_at",
                "assignee__username",
                "requester__username",
            )
            .order_by("rank", "id")[:limit]
        )

    columns = {
        "todo": col(WorkItem.Status.TODO),
        "doing": col(WorkItem.Status.DOING),
        "blocked": col(WorkItem.Status.BLOCKED),
        "done": col(WorkItem.Status.DONE),
    }

    context: Dict[str, Any] = {
        "q": q,
        "filter_status": st,
        "filter_priority": pr,
        "kpi_total": total,
        "kpi_overdue": overdue,
        "kpi_urgent": urgent,
        "kpi_done_7d": done_7d,
        "status_counts": status_counts,
        "columns": columns,
        "now": now,
        "tid": tid,
        "me": request.user,
        "shop": shop_id,
    }
    return render(request, "work/os_home.html", context)


@login_required
@require_ability(VIEW_DASHBOARD)
def os_my_work(request: HttpRequest):
    tid = _tenant_id(request)
    if not tid:
        return redirect("/dashboard/")

    u = request.user
    qs = WorkItem.objects.filter(tenant_id=tid).filter(
        Q(assignee_id=u.id) | Q(requester_id=u.id) | Q(created_by_id=u.id)
    )

    tab = (request.GET.get("tab") or "").strip().lower()  # "open" | "done"
    if tab == "done":
        qs = qs.filter(status=WorkItem.Status.DONE)
    elif tab == "open":
        qs = qs.exclude(status__in=[WorkItem.Status.DONE, WorkItem.Status.CANCELLED])

    items = qs.select_related("project", "company", "assignee").order_by("-updated_at")[:500]
    return render(request, "work/os_my_work.html", {"items": items, "tab": tab, "tid": tid})


@login_required
@require_ability(VIEW_DASHBOARD)
def os_item_detail(request: HttpRequest, item_id: int):
    tid = _tenant_id(request)
    if not tid:
        return redirect("/dashboard/")

    item = get_object_or_404(
        WorkItem.objects.select_related("project", "company", "assignee", "requester", "created_by", "shop"),
        id=item_id,
        tenant_id=tid,
    )
    comments = (
        WorkComment.objects.filter(tenant_id=tid, work_item_id=item.id)
        .select_related("actor")
        .order_by("-id")[:200]
    )

    users = _users_in_tenant(tid, shop_id=getattr(item, "shop_id", None))

    return render(
        request,
        "work/os_item_detail.html",
        {"item": item, "comments": comments, "tid": tid, "users": users},
    )


@login_required
@require_ability(VIEW_DASHBOARD)
@require_http_methods(["POST"])
def os_create_quick(request: HttpRequest):
    tid = _tenant_id(request)
    if not tid:
        return JsonResponse({"ok": False, "error": "TENANT_REQUIRED"}, status=400)

    payload = _read_json(request) if _is_json(request) else request.POST
    title = _pick_str(payload, "title")
    if not title:
        return JsonResponse({"ok": False, "error": "TITLE_REQUIRED"}, status=400)

    try:
        priority = int(payload.get("priority") or int(WorkItem.Priority.NORMAL))
    except Exception:
        priority = int(WorkItem.Priority.NORMAL)

    me = request.user if _can_use_actor(request.user) else None

    item = create_work_item(
        tenant_id=tid,
        company_id=None,
        title=title[:255],
        status=WorkItem.Status.TODO,
        created_by_id=me.id if me else None,
        requester_id=me.id if me else None,
    )

    # ✅ Phase 2: allow shop attach from form later (optional)
    shop_id = payload.get("shop_id")
    try:
        if shop_id:
            item.shop_id = int(shop_id)
    except Exception:
        pass

    item.save()

    if not (_is_ajax(request) or _is_json(request)):
        return redirect("/work/")

    return JsonResponse({"ok": True, "id": item.id})


@login_required
@require_ability(VIEW_DASHBOARD)
@require_http_methods(["POST"])
def os_transition(request: HttpRequest, item_id: int):
    tid = _tenant_id(request)
    if not tid:
        return JsonResponse({"ok": False, "error": "TENANT_REQUIRED"}, status=400)

    item = get_object_or_404(WorkItem.objects, id=item_id, tenant_id=tid)

    payload = _read_json(request) if _is_json(request) else request.POST
    to_status = _pick_str(payload, "to_status").lower()
    note = _pick_str(payload, "note")

    if not to_status:
        return JsonResponse({"ok": False, "error": "TO_STATUS_REQUIRED"}, status=400)

    try:
        item = transition_workitem(
            wi=item,
            to=to_status,
            actor=request.user,
            reason=note,
        )
    except Exception as e:
        return JsonResponse(
            {"ok": False, "error": "TRANSITION_FAILED", "detail": str(e), "to_status": to_status},
            status=400,
        )

    if not (_is_ajax(request) or _is_json(request)):
        return redirect(f"/work/item/{item.id}/")

    return JsonResponse({"ok": True, "id": item.id, "status": item.status, "status_label": _status_label(item.status)})


@login_required
@require_ability(VIEW_DASHBOARD)
@require_http_methods(["POST"])
def os_assign(request: HttpRequest, item_id: int):
    tid = _tenant_id(request)
    if not tid:
        return JsonResponse({"ok": False, "error": "TENANT_REQUIRED"}, status=400)

    item = get_object_or_404(WorkItem.objects.select_related("shop"), id=item_id, tenant_id=tid)

    payload = _read_json(request) if _is_json(request) else request.POST
    assignee_id = payload.get("assignee_id")
    if not assignee_id:
        return JsonResponse({"ok": False, "error": "ASSIGNEE_REQUIRED"}, status=400)

    try:
        assignee_id = int(assignee_id)
    except Exception:
        return JsonResponse({"ok": False, "error": "ASSIGNEE_INVALID"}, status=400)

    # ✅ security: must belong to tenant (and to shop if item has shop)
    if not _user_belongs_to_tenant(tid, assignee_id, shop_id=getattr(item, "shop_id", None)):
        return JsonResponse({"ok": False, "error": "USER_NOT_IN_TENANT_OR_SHOP"}, status=400)

    u = get_object_or_404(User, id=assignee_id, is_active=True)

    item.assignee = u
    item.save(update_fields=["assignee", "updated_at"])

    if not (_is_ajax(request) or _is_json(request)):
        return redirect(f"/work/item/{item.id}/")

    return JsonResponse({"ok": True, "id": item.id, "assignee": u.username})

@login_required
@require_ability(VIEW_DASHBOARD)
@require_http_methods(["POST"])
def os_update_meta(request: HttpRequest, item_id: int):
    tid = _tenant_id(request)
    if not tid:
        return JsonResponse({"ok": False, "error": "TENANT_REQUIRED"}, status=400)

    item = get_object_or_404(WorkItem.objects, id=item_id, tenant_id=tid)

    payload = _read_json(request) if _is_json(request) else request.POST

    # visible_to_client
    vtc = payload.get("visible_to_client")
    item.visible_to_client = str(vtc).lower() in ("1", "true", "yes", "on")

    # type
    t = _pick_str(payload, "type").lower()
    if t in dict(WorkItem.Type.choices):
        item.type = t

    # shop_id (optional)
    shop_id = payload.get("shop_id")
    try:
        item.shop_id = int(shop_id) if shop_id else None
    except Exception:
        item.shop_id = None

    item.save(update_fields=["visible_to_client", "type", "shop", "updated_at"])

    if not (_is_ajax(request) or _is_json(request)):
        return redirect(f"/work/item/{item.id}/")

    return JsonResponse({"ok": True, "id": item.id, "visible_to_client": item.visible_to_client, "type": item.type, "shop_id": item.shop_id})