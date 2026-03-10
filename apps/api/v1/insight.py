from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.apps import apps
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.shops.models import Shop
from apps.work.models import WorkItem


def _get_tenant_id(request) -> Optional[int]:
    # 1) membership active của user hiện tại
    try:
        user = getattr(request, "user", None)
        if user and getattr(user, "is_authenticated", False):
            from apps.accounts.models import Membership

            m = (
                Membership.objects.filter(user=user, is_active=True)
                .select_related("tenant", "company")
                .order_by("id")
                .first()
            )
            if m and getattr(m, "tenant_id", None):
                return int(m.tenant_id)
    except Exception:
        pass

    # 2) actor context
    try:
        actor_ctx = getattr(request, "actor_ctx", None)
        tid = getattr(actor_ctx, "tenant_id", None)
        if tid is not None:
            return int(tid)
    except Exception:
        pass

    # 3) fallback từ request
    try:
        tid = getattr(request, "tenant_id", None)
        if tid is not None:
            return int(tid)
    except Exception:
        pass

    return None


def _safe_get_model(app_label: str, model_name: str):
    try:
        return apps.get_model(app_label, model_name)
    except Exception:
        return None


def _iso(dt) -> str:
    try:
        return dt.isoformat() if dt else ""
    except Exception:
        return ""


def _calc_task_metrics(qs):
    # qs: WorkItem queryset (already scoped)
    now = timezone.now()
    soon = now + timedelta(days=7)

    open_qs = qs.exclude(status__in=["done", "cancelled"])
    blocked = open_qs.filter(status="blocked").count()
    urgent = open_qs.filter(priority__gte=4).count()
    due_overdue = open_qs.filter(due_at__isnull=False, due_at__lt=now).count()
    due_soon = open_qs.filter(due_at__isnull=False, due_at__gte=now, due_at__lte=soon).count()

    return {
        "open": open_qs.count(),
        "blocked": blocked,
        "urgent": urgent,
        "overdue": due_overdue,
        "due_soon_7d": due_soon,
    }


def _pick_top_tasks(qs, limit: int = 10):
    # ưu tiên: overdue -> blocked -> urgent -> updated
    now = timezone.now()
    open_qs = qs.exclude(status__in=["done", "cancelled"])

    overdue = open_qs.filter(due_at__isnull=False, due_at__lt=now).order_by("due_at", "-priority", "-updated_at")[:limit]
    if overdue:
        return list(
            overdue.values(
                "id",
                "title",
                "status",
                "priority",
                "shop_id",
                "company_id",
                "project_id",
                "due_at",
                "updated_at",
                "assignee_id",
                "requester_id",
            )
        )

    blocked = open_qs.filter(status="blocked").order_by("-priority", "-updated_at")[:limit]
    if blocked:
        return list(blocked.values("id", "title", "status", "priority", "shop_id", "company_id", "project_id", "due_at", "updated_at", "assignee_id", "requester_id"))

    urgent = open_qs.filter(priority__gte=4).order_by("due_at", "-updated_at")[:limit]
    return list(urgent.values("id", "title", "status", "priority", "shop_id", "company_id", "project_id", "due_at", "updated_at", "assignee_id", "requester_id"))


def _events_metrics(tenant_id: int) -> Dict[str, Any]:
    """
    Optional: nếu có apps.events.models.Event / OutboxEvent thì show.
    Không có thì trả rỗng, KHÔNG crash.
    """
    Event = _safe_get_model("events", "Event")
    if not Event:
        Event = _safe_get_model("events", "OutboxEvent") or _safe_get_model("events", "EventOutbox")

    if not Event:
        return {"supported": False}

    qs = Event.objects.filter(tenant_id=tenant_id)
    total = qs.count()

    pending = None
    failed = None
    for st_field in ("status", "state"):
        if hasattr(Event, st_field):
            try:
                pending = qs.filter(**{st_field: "pending"}).count()
                failed = qs.filter(**{st_field: "failed"}).count()
            except Exception:
                pending = pending
                failed = failed
            break

    last_50 = list(
        qs.order_by("-id")[:50].values(
            "id",
            "name",
            "version",
            "tenant_id",
            "company_id",
            "shop_id",
            "created_at",
        )
    )

    return {
        "supported": True,
        "total": total,
        "pending": pending,
        "failed": failed,
        "recent": last_50,
    }


def _health_score_for_shop(tenant_id: int, shop_id: int) -> Optional[Dict[str, Any]]:
    try:
        from apps.intelligence.shop_health import evaluate_and_emit_shop_health  # type: ignore

        res = evaluate_and_emit_shop_health(tenant_id=tenant_id, shop_id=shop_id)
        score = res.get("score") or {}
        return {
            "score": score.get("score"),
            "level": score.get("level"),
            "alerts": res.get("alerts") or [],
        }
    except Exception:
        return None


class FounderInsightApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant_id = _get_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "tenant_id missing"}, status=400)

        now = timezone.now()

        shops = list(Shop.objects_all.filter(tenant_id=tenant_id).order_by("-id")[:50].values("id", "name"))
        base_qs = WorkItem.objects_all.filter(tenant_id=tenant_id)

        overall_tasks = _calc_task_metrics(base_qs)

        per_shop: List[Dict[str, Any]] = []
        recommendations: List[Dict[str, Any]] = []
        alerts: List[Dict[str, Any]] = []

        for s in shops:
            sid = int(s["id"])
            sqs = base_qs.filter(shop_id=sid)

            m = _calc_task_metrics(sqs)
            top_tasks = _pick_top_tasks(sqs, limit=8)

            health = _health_score_for_shop(tenant_id, sid)

            if m["overdue"] >= 3:
                alerts.append({"shop_id": sid, "type": "tasks_overdue", "level": "high", "message": f"{m['overdue']} task quá hạn"})
            if m["blocked"] >= 2:
                alerts.append({"shop_id": sid, "type": "tasks_blocked", "level": "high", "message": f"{m['blocked']} task bị blocked"})
            if m["urgent"] >= 3:
                alerts.append({"shop_id": sid, "type": "tasks_urgent", "level": "medium", "message": f"{m['urgent']} task urgent"})

            if health and (health.get("level") in {"bad", "critical"} or (health.get("score") is not None and health.get("score", 0) < 50)):
                alerts.append({"shop_id": sid, "type": "shop_health", "level": "high", "message": f"Shop health thấp: {health.get('score')} ({health.get('level')})"})

            if m["overdue"] > 0:
                recommendations.append(
                    {
                        "shop_id": sid,
                        "action": "focus_overdue",
                        "priority": "P0",
                        "message": "Dồn lực xử lý task quá hạn trước (overdue)",
                    }
                )
            if m["blocked"] > 0:
                recommendations.append(
                    {
                        "shop_id": sid,
                        "action": "unblock_tasks",
                        "priority": "P0",
                        "message": "Gỡ blocked: thiếu info/thiếu duyệt/thiếu owner → chốt người chịu trách nhiệm",
                    }
                )
            if m["urgent"] > 0 and m["open"] > 10:
                recommendations.append(
                    {
                        "shop_id": sid,
                        "action": "reduce_wip",
                        "priority": "P1",
                        "message": "Giảm WIP: giới hạn task Doing, đẩy về Todo, tránh dàn trải",
                    }
                )

            per_shop.append(
                {
                    "shop_id": sid,
                    "shop_name": s.get("name") or "",
                    "health": health,
                    "tasks": m,
                    "top_tasks": [
                        {
                            **t,
                            "due_at": _iso(t.get("due_at")),
                            "updated_at": _iso(t.get("updated_at")),
                        }
                        for t in top_tasks
                    ],
                }
            )

        events = _events_metrics(tenant_id)

        seen = set()
        dedup_recs = []
        for r in recommendations:
            k = f"{r.get('shop_id')}::{r.get('action')}"
            if k in seen:
                continue
            seen.add(k)
            dedup_recs.append(r)

        return Response(
            {
                "ok": True,
                "generated_at": now.isoformat(),
                "tenant_id": tenant_id,
                "overview": {
                    "tasks": overall_tasks,
                    "events": events,
                },
                "alerts": alerts[:100],
                "recommendations": dedup_recs[:100],
                "shops": per_shop,
            }
        )