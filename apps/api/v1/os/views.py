# apps/api/v1/os/views.py
from __future__ import annotations

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.intelligence.shop_health import evaluate_and_emit_shop_health

from apps.shops.models import Shop
from apps.work.models import WorkItem


class OsCentralDashboardApi(APIView):
    """
    HeightTech Central OS

    Endpoint:
    /api/v1/os/dashboard/

    Returns:
    - shop health
    - urgent tasks
    - blocked tasks
    - recent activity
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):

        tenant_id = getattr(request, "tenant_id", None)

        if not tenant_id:
            return Response({"ok": False, "error": "tenant_id missing"}, status=400)

        shops = Shop.objects_all.filter(tenant_id=tenant_id)[:20]

        shop_health = []
        for s in shops:
            try:
                health = evaluate_and_emit_shop_health(
                    tenant_id=tenant_id,
                    shop_id=s.id,
                )
                shop_health.append(
                    {
                        "shop_id": s.id,
                        "shop_name": getattr(s, "name", ""),
                        "score": health["score"]["score"],
                        "level": health["score"]["level"],
                        "alerts": health.get("alerts", []),
                    }
                )
            except Exception:
                pass

        work_qs = WorkItem.objects_all.filter(tenant_id=tenant_id)

        open_tasks = work_qs.exclude(status__in=["done", "cancelled"]).count()

        urgent_tasks = (
            work_qs.filter(priority__gte=4)
            .exclude(status__in=["done", "cancelled"])
            .count()
        )

        blocked_tasks = work_qs.filter(status="blocked").count()

        recent_work = (
            work_qs.order_by("-updated_at", "-id")[:20]
            .values(
                "id",
                "title",
                "status",
                "priority",
                "shop_id",
                "company_id",
                "updated_at",
            )
        )

        return Response(
            {
                "ok": True,
                "generated_at": timezone.now(),
                "tenant_id": tenant_id,
                "shops_health": shop_health,
                "tasks": {
                    "open": open_tasks,
                    "urgent": urgent_tasks,
                    "blocked": blocked_tasks,
                },
                "recent_activity": list(recent_work),
            }
        )