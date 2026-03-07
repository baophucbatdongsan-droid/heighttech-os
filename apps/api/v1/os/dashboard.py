# apps/api/v1/os/dashboard.py
from __future__ import annotations

from typing import Any, Dict, Optional

from django.apps import apps
from django.db import models
from django.db.models import Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import AbilityPermission, VIEW_API_DASHBOARD, resolve_user_role


def _get_model(app_label: str, model_name: str):
    try:
        return apps.get_model(app_label, model_name)
    except Exception:
        return None


def _has_field(Model, field_name: str) -> bool:
    try:
        Model._meta.get_field(field_name)
        return True
    except Exception:
        return False


def _safe_int(v, default=0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _resolve_tenant_id(request) -> Optional[int]:
    """
    Ưu tiên các convention sẵn có trong codebase anh:
    - request.tenant_id (middleware)
    - request.tenant.id (TenantRequiredMixin)
    - header X-Tenant-Id (fallback)
    """
    tid = getattr(request, "tenant_id", None)
    if tid:
        return _safe_int(tid, None)

    tenant = getattr(request, "tenant", None)
    if tenant and getattr(tenant, "id", None):
        return _safe_int(tenant.id, None)

    try:
        h = request.headers.get("X-Tenant-Id")
        if h:
            return _safe_int(h, None)
    except Exception:
        pass

    return None


def _shop_counts(tenant_id: int) -> Dict[str, Any]:
    Shop = _get_model("shops", "Shop")
    if not Shop:
        return {"ok": False, "message": "Không tìm thấy model Shop", "total": 0, "active": 0, "risk": 0, "items": []}

    qs = Shop.objects_all.filter(tenant_id=tenant_id)
    total = qs.count()

    # active heuristic
    if _has_field(Shop, "is_active"):
        active = qs.filter(is_active=True).count()
    elif _has_field(Shop, "status"):
        active = qs.filter(status__in=["active", "running", "enabled"]).count()
    else:
        active = total

    # risk heuristic
    risk_q = Q()
    if _has_field(Shop, "health_score"):
        risk_q |= Q(health_score__lt=60)
    if _has_field(Shop, "risk_level"):
        risk_q |= Q(risk_level__in=["high", "critical"])
    if _has_field(Shop, "status"):
        risk_q |= Q(status__in=["paused", "inactive", "risk", "blocked"])

    risk = qs.filter(risk_q).count() if str(risk_q) != "(AND: )" else 0

    # top list
    items = []
    pick_fields = ["id"]
    for f in ["name", "title", "slug", "status", "health_score", "updated_at"]:
        if _has_field(Shop, f):
            pick_fields.append(f)

    for s in qs.order_by("-id").only(*pick_fields)[:10]:
        items.append(
            {
                "id": getattr(s, "id", None),
                "ten": getattr(s, "name", None)
                or getattr(s, "title", None)
                or getattr(s, "slug", None)
                or f"Shop#{s.id}",
                "trang_thai": getattr(s, "status", None),
                "suc_khoe": getattr(s, "health_score", None),
                "cap_nhat": getattr(s, "updated_at", None).isoformat() if getattr(s, "updated_at", None) else None,
            }
        )

    return {"ok": True, "total": total, "active": active, "risk": risk, "items": items}


def _work_counts(tenant_id: int) -> Dict[str, Any]:
    WorkItem = _get_model("work", "WorkItem")
    if not WorkItem:
        return {"ok": False, "message": "Không tìm thấy model WorkItem", "total_open": 0, "overdue": 0, "by_status": {}, "recent": []}

    qs = WorkItem.objects_all.filter(tenant_id=tenant_id)

    total_open = qs.exclude(status__in=["done", "cancelled"]).count()

    now = timezone.now()
    overdue = (
        qs.filter(due_at__isnull=False, due_at__lt=now)
        .exclude(status__in=["done", "cancelled"])
        .count()
    )

    by_status = {}
    for st in ["todo", "doing", "blocked", "done", "cancelled"]:
        by_status[st] = qs.filter(status=st).count()

    recent = []
    pick_fields = ["id", "title", "status", "priority", "updated_at"]
    for f in ["project_id", "shop_id", "assignee_id"]:
        if _has_field(WorkItem, f):
            pick_fields.append(f)

    for it in qs.order_by("-updated_at", "-id").only(*pick_fields)[:15]:
        recent.append(
            {
                "id": it.id,
                "tieu_de": getattr(it, "title", ""),
                "trang_thai": getattr(it, "status", ""),
                "uu_tien": getattr(it, "priority", None),
                "project_id": getattr(it, "project_id", None),
                "shop_id": getattr(it, "shop_id", None),
                "assignee_id": getattr(it, "assignee_id", None),
                "cap_nhat": getattr(it, "updated_at", None).isoformat() if getattr(it, "updated_at", None) else None,
            }
        )

    return {"ok": True, "total_open": total_open, "overdue": overdue, "by_status": by_status, "recent": recent}


def _projects_counts(tenant_id: int) -> Dict[str, Any]:
    Project = _get_model("projects", "Project")
    if not Project:
        return {"ok": False, "message": "Không tìm thấy model Project", "total": 0, "active": 0}

    qs = Project.objects_all.filter(tenant_id=tenant_id)
    total = qs.count()

    if _has_field(Project, "status"):
        active = qs.filter(status__in=["active", "running"]).count()
    else:
        active = total

    return {"ok": True, "total": total, "active": active}


def _actions_counts(tenant_id: int) -> Dict[str, Any]:
    Action = _get_model("actions", "FounderAction") or _get_model("actions", "Action") or _get_model("core", "Action")
    if not Action:
        return {"ok": True, "total_open": 0, "critical": 0, "items": []}

    qs = Action.objects_all.filter(tenant_id=tenant_id)

    if _has_field(Action, "status"):
        total_open = qs.filter(status__in=["open", "todo", "pending"]).count()
    else:
        total_open = qs.count()

    if _has_field(Action, "severity"):
        critical = qs.filter(severity__in=["critical", "high"]).count()
    elif _has_field(Action, "priority"):
        critical = qs.filter(priority__gte=3).count()
    else:
        critical = 0

    items = []
    pick_fields = ["id"]
    for f in ["title", "name", "status", "severity", "priority", "updated_at", "created_at"]:
        if _has_field(Action, f):
            pick_fields.append(f)

    for a in qs.order_by("-id").only(*pick_fields)[:10]:
        items.append(
            {
                "id": getattr(a, "id", None),
                "tieu_de": getattr(a, "title", None) or getattr(a, "name", None) or f"Action#{a.id}",
                "trang_thai": getattr(a, "status", None),
                "muc_do": getattr(a, "severity", None),
                "uu_tien": getattr(a, "priority", None),
                "cap_nhat": (
                    getattr(a, "updated_at", None) or getattr(a, "created_at", None)
                ).isoformat() if (getattr(a, "updated_at", None) or getattr(a, "created_at", None)) else None,
            }
        )

    return {"ok": True, "total_open": total_open, "critical": critical, "items": items}


def _revenue_snapshot(tenant_id: int) -> Dict[str, Any]:
    Performance = _get_model("performance", "Performance") or _get_model("performance", "MonthlyPerformance")
    if not Performance:
        return {"ok": True, "today_gmv": None, "today_profit": None, "ghi_chu": "Chưa nối model performance"}

    qs = Performance.objects_all.filter(tenant_id=tenant_id)

    today = timezone.localdate()
    if _has_field(Performance, "date"):
        qs = qs.filter(date=today)
    elif _has_field(Performance, "created_at"):
        qs = qs.filter(created_at__date=today)

    today_gmv = None
    today_profit = None

    if _has_field(Performance, "gmv"):
        try:
            today_gmv = qs.aggregate(v=models.Sum("gmv"))["v"]
        except Exception:
            pass

    if _has_field(Performance, "profit"):
        try:
            today_profit = qs.aggregate(v=models.Sum("profit"))["v"]
        except Exception:
            pass

    return {"ok": True, "today_gmv": today_gmv, "today_profit": today_profit}


class OSDashboardApi(APIView):
    """
    GET /api/v1/os/dashboard/
    """
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def get(self, request, *args, **kwargs):
        tenant_id = _resolve_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        role = resolve_user_role(request.user)

        payload: Dict[str, Any] = {
            "ok": True,
            "role": role,
            "tenant_id": int(tenant_id),
            "generated_at": timezone.now().isoformat(),
            "system": {"timezone": str(timezone.get_current_timezone())},
            "shops": _shop_counts(int(tenant_id)),
            "projects": _projects_counts(int(tenant_id)),
            "work": _work_counts(int(tenant_id)),
            "actions": _actions_counts(int(tenant_id)),
            "revenue": _revenue_snapshot(int(tenant_id)),
        }

        payload["headline"] = {
            "shops_total": payload["shops"].get("total", 0),
            "shops_risk": payload["shops"].get("risk", 0),
            "work_open": payload["work"].get("total_open", 0),
            "work_overdue": payload["work"].get("overdue", 0),
            "actions_open": payload["actions"].get("total_open", 0),
            "actions_critical": payload["actions"].get("critical", 0),
        }

        return Response(payload)