from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Optional, List

from django.db.models import Count, Q
from django.utils import timezone

from apps.projects.models import Project
from apps.projects.types import normalize_project_type, get_type_display_safe

from apps.rules.resolver import get_engine
from apps.rules.types import EngineContext
from datetime import date

DOMAIN = "projects_dashboard"
DEFAULT_RULE_VERSION = "v1"


@dataclass
class ProjectDashboardResult:
    summary: Dict[str, Any]
    items: List[Dict[str, Any]]


class ProjectDashboardService:
    """
    Dashboard cho projects theo tenant + scope company.
    - Founder/superuser: xem all trong tenant (có thể filter company_id)
    - Company user: chỉ xem company đó
    """

    @staticmethod
    def build(
        *,
        tenant_id: int,
        company_id: Optional[int] = None,
        limit: int = 50,
    ) -> ProjectDashboardResult:
        qs = Project.objects_all.filter(tenant_id=tenant_id).order_by("-id")
        if company_id is not None:
            qs = qs.filter(company_id=company_id)
        return ProjectDashboardService.build_from_queryset(qs, limit=limit)

    @staticmethod
    def build_from_queryset(qs, *, limit: int = 50) -> ProjectDashboardResult:
        """
        Dùng khi page đã filter/paginate sẵn queryset.
        """
        qs = qs.annotate(
            shops_total=Count("project_shops", distinct=True),
            shops_active=Count("project_shops", filter=Q(project_shops__status="active"), distinct=True),
            shops_paused=Count("project_shops", filter=Q(project_shops__status="paused"), distinct=True),
            shops_done=Count("project_shops", filter=Q(project_shops__status="done"), distinct=True),
            shops_inactive=Count("project_shops", filter=Q(project_shops__status="inactive"), distinct=True),
        )

        lim = max(1, min(int(limit or 50), 200))

        items: List[Dict[str, Any]] = []
        for p in qs[:lim]:
            total = int(getattr(p, "shops_total", 0) or 0)
            done = int(getattr(p, "shops_done", 0) or 0)
            paused = int(getattr(p, "shops_paused", 0) or 0)
            inactive = int(getattr(p, "shops_inactive", 0) or 0)

            type_code = normalize_project_type(getattr(p, "type", None)) or "default"
            type_display = get_type_display_safe(p)

            # optional: nếu model có field rule_version thì dùng, không có thì fallback
            rule_version = getattr(p, "rule_version", None) or DEFAULT_RULE_VERSION

            spec = RuleRegistry.resolve(
                domain=DOMAIN,
                key=type_code,
                rule_version=rule_version,
                on_date=date.today(),
                default_key="default",
            )

            if spec:
                computed_progress, computed_health = spec.fn(
                    total=total, done=done, paused=paused, inactive=inactive
                )
            else:
                # fallback cực an toàn
                computed_progress = int(round((done / total) * 100)) if total else 0
                computed_health = 100

            items.append(
                {
                    "id": p.id,
                    "tenant_id": p.tenant_id,
                    "company_id": p.company_id,
                    "name": p.name,
                    "type": type_display,     # display
                    "type_code": type_code,   # canonical

                    # (optional) cho debug/trace version đang áp
                    "rule_version": rule_version,

                    "status": p.status,
                    "created_at": getattr(p, "created_at", None),
                    "updated_at": getattr(p, "updated_at", None),
                    "last_activity_at": getattr(p, "last_activity_at", None),
                    "progress_percent": int(getattr(p, "progress_percent", 0) or computed_progress),
                    "health_score": int(getattr(p, "health_score", 100) or computed_health),
                    "shops": {
                        "total": total,
                        "active": int(getattr(p, "shops_active", 0) or 0),
                        "paused": paused,
                        "done": done,
                        "inactive": inactive,
                    },
                }
            )

        by_status: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        health_buckets = {"0_39": 0, "40_69": 0, "70_100": 0}

        for it in items:
            by_status[it["status"]] = by_status.get(it["status"], 0) + 1

            # summary dùng type_code để không bị split key
            tcode = it.get("type_code") or normalize_project_type(it.get("type"))
            by_type[tcode] = by_type.get(tcode, 0) + 1

            hs = int(it["health_score"] or 0)
            if hs <= 39:
                health_buckets["0_39"] += 1
            elif hs <= 69:
                health_buckets["40_69"] += 1
            else:
                health_buckets["70_100"] += 1

        top_risk = sorted(items, key=lambda x: (x["health_score"], -(x["shops"]["total"] or 0)))[:10]

        summary = {
            "total_projects": len(items),
            "by_status": by_status,
            "by_type": by_type,
            "health_buckets": health_buckets,
            "top_risk": top_risk,
            "generated_at": timezone.now(),
        }
        return ProjectDashboardResult(summary=summary, items=items)