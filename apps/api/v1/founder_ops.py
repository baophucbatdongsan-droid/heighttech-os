from __future__ import annotations

from typing import Any, Dict, List, Optional

from django.db.models import Count
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.base import TenantRequiredMixin
from apps.api.v1.permissions import AbilityPermission
from apps.core.policy import VIEW_API_FOUNDER

from apps.work.models import WorkItem

try:
    from apps.intelligence.models import ShopActionItem
except Exception:
    ShopActionItem = None  # type: ignore


DONE_STATUSES = ["done", "cancelled"]
DEFAULT_TOP = 5
MAX_TOP = 20


# -----------------------------------------------------
# helpers
# -----------------------------------------------------
def _risk_level(score: int) -> str:
    if score >= 700:
        return "CRITICAL"
    if score >= 400:
        return "HIGH"
    if score >= 200:
        return "MEDIUM"
    return "LOW"


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _parse_top_param(request) -> int:
    raw = request.query_params.get("top")
    if not raw:
        return DEFAULT_TOP
    try:
        v = int(raw)
        if v <= 0:
            return DEFAULT_TOP
        return min(v, MAX_TOP)
    except Exception:
        return DEFAULT_TOP


def _top_from_rows(rows: List[Dict[str, Any]], id_key: str, count_key: str, name_map: Optional[Dict[int, str]] = None):
    out = []
    for r in rows:
        _id = r.get(id_key)
        if not _id:
            continue
        _id = _safe_int(_id)
        if _id <= 0:
            continue

        out.append(
            {
                "id": _id,
                "name": (name_map or {}).get(_id, ""),
                "overdue": _safe_int(r.get(count_key)),
            }
        )
    return out


# =====================================================
# API
# =====================================================
class FounderOpsOverviewApi(TenantRequiredMixin, APIView):
    """
    GET /api/v1/founder/ops/overview/?top=5
    """

    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_FOUNDER

    def get(self, request):
        tenant = self.get_tenant()
        tenant_id = int(tenant.id)
        now = timezone.now()
        top_limit = _parse_top_param(request)

        # -------------------------
        # WorkItems (tenant scoped)
        # -------------------------
        work_qs = WorkItem.objects_all.filter(tenant_id=tenant_id)

        total = work_qs.count()

        by_status_rows = work_qs.values("status").annotate(c=Count("id"))
        by_status = {r["status"]: r["c"] for r in by_status_rows}

        overdue_qs = work_qs.filter(due_at__lt=now).exclude(status__in=DONE_STATUSES)
        overdue = overdue_qs.count()

        blocked = work_qs.filter(status="blocked").count()

        # -------------------------
        # Actions (optional intelligence)
        # -------------------------
        p0_open = 0
        p1_open = 0

        if ShopActionItem is not None:
            a_qs = ShopActionItem.objects.all()

            if hasattr(ShopActionItem, "tenant_id"):
                a_qs = a_qs.filter(tenant_id=tenant_id)

            if hasattr(ShopActionItem, "closed_at"):
                a_qs = a_qs.filter(closed_at__isnull=True)

            if hasattr(ShopActionItem, "severity"):
                p0_open = a_qs.filter(severity="P0").count()
                p1_open = a_qs.filter(severity="P1").count()

        # -------------------------
        # Top risk sources
        # -------------------------
        top_company_rows = (
            overdue_qs.exclude(company_id__isnull=True)
            .values("company_id")
            .annotate(overdue_count=Count("id"))
            .order_by("-overdue_count", "-company_id")[:top_limit]
        )

        top_project_rows = (
            overdue_qs.exclude(project_id__isnull=True)
            .values("project_id")
            .annotate(overdue_count=Count("id"))
            .order_by("-overdue_count", "-project_id")[:top_limit]
        )

        company_name_map: Dict[int, str] = {}
        project_name_map: Dict[int, str] = {}

        try:
            from apps.companies.models import Company

            ids = [int(r["company_id"]) for r in top_company_rows if r.get("company_id")]
            for c in Company.objects_all.filter(id__in=ids).only("id", "name"):
                company_name_map[int(c.id)] = getattr(c, "name", "") or ""
        except Exception:
            pass

        try:
            from apps.projects.models import Project

            ids = [int(r["project_id"]) for r in top_project_rows if r.get("project_id")]
            for p in Project.objects_all.filter(id__in=ids).only("id", "name"):
                project_name_map[int(p.id)] = getattr(p, "name", "") or ""
        except Exception:
            pass

        top_companies = _top_from_rows(list(top_company_rows), "company_id", "overdue_count", company_name_map)
        top_projects = _top_from_rows(list(top_project_rows), "project_id", "overdue_count", project_name_map)

        # -------------------------
        # Risk score
        # -------------------------
        overdue_weight = overdue * 5
        blocked_weight = blocked * 3
        p0_weight = p0_open * 20
        p1_weight = p1_open * 10

        score = overdue_weight + blocked_weight + p0_weight + p1_weight
        level = _risk_level(score)

        recommendations: List[str] = []
        if overdue > 0:
            recommendations.append("Reduce overdue tasks immediately (clear backlog).")
        if blocked > 0:
            recommendations.append("Investigate blocked tasks – possible dependency bottleneck.")
        if level in ("HIGH", "CRITICAL"):
            recommendations.append(f"System risk is {level} – require management intervention.")

        return Response(
            {
                "ok": True,
                "tenant_id": tenant_id,
                "risk": {
                    "score": score,
                    "level": level,
                },
                "work_items": {
                    "total": total,
                    "overdue": overdue,
                    "blocked": blocked,
                    "by_status": by_status,
                },
                "actions": {
                    "p0_open": p0_open,
                    "p1_open": p1_open,
                },
                "top_risk_sources": {
                    "companies": top_companies,
                    "projects": top_projects,
                },
                "recommendations": recommendations,
            }
        )