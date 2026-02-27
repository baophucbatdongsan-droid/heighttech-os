# apps/api/v1/work/views_analytics.py
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.guards import get_scope_company_ids, get_scope_shop_ids
from apps.core.permissions import (
    AbilityPermission,
    VIEW_API_DASHBOARD,
    resolve_user_role,
    ROLE_CLIENT,
    ROLE_FOUNDER,
)
from apps.work.models import WorkItem

DONE_STATUSES = ["done", "cancelled"]


def _parse_int(v: Any, default: int) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _scope_queryset_for_user(request, qs):
    """
    Scope dữ liệu cho user:
    - Founder/superuser: thấy hết trong tenant
    - Staff: theo company scope / shop scope (và suy ra channel/booking)
    - Client: theo shop scope nhưng chỉ thấy task public (is_internal=False)
    """
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


# =====================================================
# ANALYTICS ENDPOINTS (TÊN CHUẨN)
# =====================================================

class WorkAnalyticsWorkloadView(APIView):
    """
    GET /api/v1/work/analytics/workload/

    Query:
      - days (mặc định 30)
      - include_done=1 (mặc định 0)
      - top (mặc định 10)
    """
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def get(self, request, *args, **kwargs):
        qs = _scope_queryset_for_user(request, WorkItem.objects_all.all())

        days = _parse_int(request.query_params.get("days"), 30)
        top = _parse_int(request.query_params.get("top"), 10)
        include_done = str(request.query_params.get("include_done") or "").strip().lower() in {"1", "true", "yes"}

        now = timezone.now()
        if days > 0:
            qs = qs.filter(updated_at__gte=now - timedelta(days=days))

        if not include_done:
            qs = qs.exclude(status__in=DONE_STATUSES)

        rows = (
            qs.exclude(assignee_id__isnull=True)
            .values("assignee_id")
            .annotate(
                total=Count("id"),
                todo=Count("id", filter=Q(status="todo")),
                doing=Count("id", filter=Q(status="doing")),
                blocked=Count("id", filter=Q(status="blocked")),
                overdue=Count("id", filter=Q(due_at__lt=now) & ~Q(status__in=DONE_STATUSES)),
            )
            .order_by("-total", "-assignee_id")[: max(top, 1)]
        )

        items = []
        for r in rows:
            items.append(
                {
                    "assignee_id": int(r["assignee_id"]),
                    "total": int(r["total"]),
                    "by_status": {
                        "todo": int(r["todo"]),
                        "doing": int(r["doing"]),
                        "blocked": int(r["blocked"]),
                    },
                    "overdue": int(r["overdue"]),
                }
            )

        return Response({"ok": True, "days": days, "include_done": include_done, "top": top, "items": items})


class WorkAnalyticsOverdueView(APIView):
    """
    GET /api/v1/work/analytics/overdue/

    Query:
      - top (mặc định 10)
    """
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def get(self, request, *args, **kwargs):
        now = timezone.now()
        qs = _scope_queryset_for_user(request, WorkItem.objects_all.all())
        overdue_qs = qs.filter(due_at__lt=now).exclude(status__in=DONE_STATUSES)

        top = _parse_int(request.query_params.get("top"), 10)

        def _bucket(days: int):
            return now - timedelta(days=days)

        od_0_2 = overdue_qs.filter(due_at__gte=_bucket(2)).count()
        od_3_7 = overdue_qs.filter(due_at__lt=_bucket(2), due_at__gte=_bucket(7)).count()
        od_8_30 = overdue_qs.filter(due_at__lt=_bucket(7), due_at__gte=_bucket(30)).count()
        od_31p = overdue_qs.filter(due_at__lt=_bucket(30)).count()

        top_company_rows = (
            overdue_qs.exclude(company_id__isnull=True)
            .values("company_id")
            .annotate(overdue_count=Count("id"))
            .order_by("-overdue_count", "-company_id")[: max(top, 1)]
        )

        top_project_rows = (
            overdue_qs.exclude(project_id__isnull=True)
            .values("project_id")
            .annotate(overdue_count=Count("id"))
            .order_by("-overdue_count", "-project_id")[: max(top, 1)]
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

        top_companies = [
            {
                "id": int(r["company_id"]),
                "name": company_name_map.get(int(r["company_id"]), ""),
                "overdue": int(r["overdue_count"]),
            }
            for r in top_company_rows
            if r.get("company_id")
        ]
        top_projects = [
            {
                "id": int(r["project_id"]),
                "name": project_name_map.get(int(r["project_id"]), ""),
                "overdue": int(r["overdue_count"]),
            }
            for r in top_project_rows
            if r.get("project_id")
        ]

        return Response(
            {
                "ok": True,
                "total_overdue": overdue_qs.count(),
                "buckets": {
                    "0_2_days": od_0_2,
                    "3_7_days": od_3_7,
                    "8_30_days": od_8_30,
                    "31p_days": od_31p,
                },
                "top_risk_sources": {"companies": top_companies, "projects": top_projects},
            }
        )


class WorkAnalyticsVelocityView(APIView):
    """
    GET /api/v1/work/analytics/velocity/

    Query:
      - days (mặc định 30)
    """
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def get(self, request, *args, **kwargs):
        qs = _scope_queryset_for_user(request, WorkItem.objects_all.all())
        now = timezone.now()
        days = _parse_int(request.query_params.get("days"), 30)
        if days <= 0:
            days = 30

        since = now - timedelta(days=days)

        created = qs.filter(created_at__gte=since).count()
        done = qs.filter(status="done", done_at__gte=since).count()
        cancelled = qs.filter(status="cancelled", done_at__gte=since).count()

        open_total = qs.exclude(status__in=DONE_STATUSES).count()
        blocked = qs.filter(status="blocked").count()
        overdue = qs.filter(due_at__lt=now).exclude(status__in=DONE_STATUSES).count()

        return Response(
            {
                "ok": True,
                "days": days,
                "since": since.isoformat(),
                "created": created,
                "done": done,
                "cancelled": cancelled,
                "open_total": open_total,
                "blocked": blocked,
                "overdue": overdue,
            }
        )


class WorkAnalyticsPerformanceCompanyView(APIView):
    """
    GET /api/v1/work/analytics/performance/company/

    Query:
      - top (mặc định 10)
      - days (mặc định 0 = all time). Nếu days>0 thì chỉ tính updated_at trong N ngày gần nhất.
    """
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def get(self, request, *args, **kwargs):
        qs = _scope_queryset_for_user(request, WorkItem.objects_all.all())

        top = _parse_int(request.query_params.get("top"), 10)
        days = _parse_int(request.query_params.get("days"), 0)

        now = timezone.now()
        if days and days > 0:
            qs = qs.filter(updated_at__gte=now - timedelta(days=days))

        rows = (
            qs.exclude(company_id__isnull=True)
            .values("company_id")
            .annotate(
                total=Count("id"),
                done=Count("id", filter=Q(status="done")),
                cancelled=Count("id", filter=Q(status="cancelled")),
                blocked=Count("id", filter=Q(status="blocked")),
                overdue=Count("id", filter=Q(due_at__lt=now) & ~Q(status__in=DONE_STATUSES)),
                open_total=Count("id", filter=~Q(status__in=DONE_STATUSES)),
            )
            .order_by("-overdue", "-blocked", "-open_total", "-total")[: max(top, 1)]
        )

        company_name_map: Dict[int, str] = {}
        try:
            from apps.companies.models import Company

            ids = [int(r["company_id"]) for r in rows if r.get("company_id")]
            for c in Company.objects_all.filter(id__in=ids).only("id", "name"):
                company_name_map[int(c.id)] = getattr(c, "name", "") or ""
        except Exception:
            pass

        items = []
        for r in rows:
            cid = int(r["company_id"])
            items.append(
                {
                    "company_id": cid,
                    "company_name": company_name_map.get(cid, ""),
                    "total": int(r["total"]),
                    "open_total": int(r["open_total"]),
                    "done": int(r["done"]),
                    "cancelled": int(r["cancelled"]),
                    "blocked": int(r["blocked"]),
                    "overdue": int(r["overdue"]),
                }
            )

        return Response({"ok": True, "days": days, "top": top, "items": items})


# =====================================================
# BACKWARD COMPAT ALIASES (ĐỂ KHÔNG GÃY IMPORT CŨ)
# =====================================================

# Tên “đẹp” (new)
WorkloadAnalyticsView = WorkAnalyticsWorkloadView
OverdueAnalyticsView = WorkAnalyticsOverdueView
VelocityAnalyticsView = WorkAnalyticsVelocityView
PerformanceByCompanyAnalyticsView = WorkAnalyticsPerformanceCompanyView

# Tên “cũ” (legacy)
PerformanceCompanyAnalyticsView = WorkAnalyticsPerformanceCompanyView
WorkAnalyticsPerformanceCompanyView = WorkAnalyticsPerformanceCompanyView
WorkAnalyticsDashboardView = None
WorkAnalyticsDashboardV1View = None
WorkFounderDashboardView = None
WorkFounderDashboardV1View = None