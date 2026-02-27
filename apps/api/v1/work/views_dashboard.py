# apps/api/v1/work/views_dashboard.py
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import AbilityPermission, VIEW_API_DASHBOARD, resolve_user_role, ROLE_CLIENT, ROLE_FOUNDER
from apps.api.v1.guards import get_scope_company_ids, get_scope_shop_ids
from apps.work.models import WorkItem


DONE_STATUSES = ["done", "cancelled"]
STATUSES = ["todo", "doing", "blocked", "done", "cancelled"]


def _parse_int(v: Any, default: int) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _risk_level(score: int) -> str:
    if score >= 700:
        return "CRITICAL"
    if score >= 400:
        return "HIGH"
    if score >= 200:
        return "MEDIUM"
    return "LOW"


def _scope_queryset_for_user(request, qs):
    """
    Scope dữ liệu cho user:
    - Founder/superuser: thấy hết trong tenant
    - Staff: theo company scope / shop scope
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


class WorkDashboardV1View(APIView):
    """
    GET /api/v1/work/analytics/dashboard/v1/

    Trả về JSON tổng hợp đủ để FE dựng dashboard.
    """

    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def get(self, request, *args, **kwargs):
        now = timezone.now()
        qs = _scope_queryset_for_user(request, WorkItem.objects_all.all())

        # =========================
        # 1) Kanban totals
        # =========================
        total = qs.count()
        by_status_rows = qs.values("status").annotate(c=Count("id"))
        by_status = {r["status"]: r["c"] for r in by_status_rows}
        for st in STATUSES:
            by_status.setdefault(st, 0)

        blocked = qs.filter(status="blocked").count()

        overdue_qs = qs.filter(due_at__lt=now).exclude(status__in=DONE_STATUSES)
        overdue = overdue_qs.count()

        # =========================
        # 2) Risk score (như bạn đang dùng)
        # =========================
        overdue_weight = overdue * 5
        blocked_weight = blocked * 3
        score = overdue_weight + blocked_weight
        level = _risk_level(score)

        # =========================
        # 3) Top risk sources
        # =========================
        top_n = _parse_int(request.query_params.get("top"), 5)

        top_company_rows = (
            overdue_qs.exclude(company_id__isnull=True)
            .values("company_id")
            .annotate(overdue_count=Count("id"))
            .order_by("-overdue_count", "-company_id")[:top_n]
        )
        top_project_rows = (
            overdue_qs.exclude(project_id__isnull=True)
            .values("project_id")
            .annotate(overdue_count=Count("id"))
            .order_by("-overdue_count", "-project_id")[:top_n]
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
            {"id": int(r["company_id"]), "name": company_name_map.get(int(r["company_id"]), ""), "overdue": int(r["overdue_count"])}
            for r in top_company_rows
            if r.get("company_id")
        ]
        top_projects = [
            {"id": int(r["project_id"]), "name": project_name_map.get(int(r["project_id"]), ""), "overdue": int(r["overdue_count"])}
            for r in top_project_rows
            if r.get("project_id")
        ]

        # =========================
        # 4) Analytics: workload (assignee)
        # =========================
        workload_rows = (
            qs.exclude(status__in=DONE_STATUSES)
            .exclude(assignee_id__isnull=True)
            .values("assignee_id")
            .annotate(total=Count("id"))
            .order_by("-total", "-assignee_id")[:10]
        )
        workload = [{"assignee_id": int(r["assignee_id"]), "total": int(r["total"])} for r in workload_rows]

        # =========================
        # 5) Analytics: overdue buckets
        # =========================
        def _bucket(days: int):
            return now - timedelta(days=days)

        od_0_2 = overdue_qs.filter(due_at__gte=_bucket(2)).count()
        od_3_7 = overdue_qs.filter(due_at__lt=_bucket(2), due_at__gte=_bucket(7)).count()
        od_8_30 = overdue_qs.filter(due_at__lt=_bucket(7), due_at__gte=_bucket(30)).count()
        od_31p = overdue_qs.filter(due_at__lt=_bucket(30)).count()

        overdue_buckets = {
            "0_2_days": od_0_2,
            "3_7_days": od_3_7,
            "8_30_days": od_8_30,
            "31p_days": od_31p,
        }

        # =========================
        # 6) Analytics: velocity (done last 7/30)
        # =========================
        done_7 = qs.filter(status="done", done_at__gte=now - timedelta(days=7)).count()
        done_30 = qs.filter(status="done", done_at__gte=now - timedelta(days=30)).count()
        created_7 = qs.filter(created_at__gte=now - timedelta(days=7)).count()
        created_30 = qs.filter(created_at__gte=now - timedelta(days=30)).count()

        velocity = {
            "created_last_7_days": created_7,
            "created_last_30_days": created_30,
            "done_last_7_days": done_7,
            "done_last_30_days": done_30,
        }

        # =========================
        # 7) Performance by company (basic)
        # =========================
        perf_company_rows = (
            qs.exclude(company_id__isnull=True)
            .values("company_id")
            .annotate(
                total=Count("id"),
                done=Count("id", filter=Q(status="done")),
                overdue=Count("id", filter=Q(due_at__lt=now) & ~Q(status__in=DONE_STATUSES)),
                blocked=Count("id", filter=Q(status="blocked")),
            )
            .order_by("-overdue", "-blocked", "-total")[:10]
        )
        performance_company = []
        for r in perf_company_rows:
            cid = int(r["company_id"])
            performance_company.append(
                {
                    "company_id": cid,
                    "company_name": company_name_map.get(cid, ""),
                    "total": int(r["total"]),
                    "done": int(r["done"]),
                    "overdue": int(r["overdue"]),
                    "blocked": int(r["blocked"]),
                }
            )

        # =========================
        # 8) Recommendations
        # =========================
        recs: List[str] = []
        if overdue > 0:
            recs.append("Giảm việc quá hạn ngay (dọn backlog).")
        if blocked > 0:
            recs.append("Rà soát việc bị chặn (tắc dependency/approval).")
        if level in ("HIGH", "CRITICAL"):
            recs.append(f"Rủi ro hệ thống đang {level} – cần can thiệp quản lý.")

        return Response(
            {
                "ok": True,
                "tenant_id": getattr(request, "tenant_id", None),
                "risk": {
                    "score": score,
                    "level": level,
                    "breakdown": {"overdue_weight": overdue_weight, "blocked_weight": blocked_weight},
                },
                "work_items": {
                    "total": total,
                    "overdue": overdue,
                    "blocked": blocked,
                    "by_status": by_status,
                },
                "top_risk_sources": {"companies": top_companies, "projects": top_projects},
                "analytics": {
                    "workload": workload,
                    "overdue": overdue_buckets,
                    "velocity": velocity,
                    "performance_company": performance_company,
                },
                "recommendations": recs,
            }
        )