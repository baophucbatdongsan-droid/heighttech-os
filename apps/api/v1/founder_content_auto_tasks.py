from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.contracts.models import ContractChannelContent
from apps.contracts.services_content_ai import score_content
from apps.contracts.services_content_priority import decide_priority
from apps.contracts.services_auto_workitem import ensure_auto_task_for_content


def _tenant_id_from_request(request):
    tid = request.headers.get("X-Tenant-Id")
    if tid:
        try:
            return int(tid)
        except Exception:
            pass

    tenant = getattr(request, "tenant", None)
    tid = getattr(tenant, "id", None) if tenant else None
    if tid:
        try:
            return int(tid)
        except Exception:
            pass

    tid = getattr(request, "tenant_id", None)
    if tid:
        try:
            return int(tid)
        except Exception:
            pass

    return None


class FounderContentAutoTasksGenerateApi(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        limit = request.data.get("limit", 30)
        try:
            limit = int(limit)
        except Exception:
            limit = 30
        if limit <= 0:
            limit = 30
        if limit > 100:
            limit = 100

        contents = (
            ContractChannelContent.objects_all
            .filter(tenant_id=int(tenant_id))
            .prefetch_related("daily_metrics")
            .order_by("-id")[:300]
        )

        created_or_updated = []

        for item in contents:
            metrics = []
            total_views = 0
            total_orders = 0
            total_revenue = 0

            try:
                for m in item.daily_metrics.all().order_by("-metric_date")[:14]:
                    metrics.append({
                        "views": m.views,
                        "likes": m.likes,
                        "comments": m.comments,
                        "shares": m.shares,
                        "orders": m.orders,
                        "revenue": str(m.revenue or 0),
                    })
                    total_views += int(m.views or 0)
                    total_orders += int(m.orders or 0)
                    total_revenue += float(m.revenue or 0)
            except Exception:
                pass

            ai = score_content(metrics)
            row = {
                "status": item.status,
                "views_14d": total_views,
                "orders_14d": total_orders,
                "revenue_14d": total_revenue,
                "ai": ai,
            }
            priority = decide_priority(row)

            if priority.get("priority_label") not in ("scale_now", "produce_now", "fix_now"):
                continue

            work = ensure_auto_task_for_content(
                tenant_id=int(tenant_id),
                content=item,
                priority=priority,
                ai=ai,
                assignee_id=None,
            )

            created_or_updated.append({
                "content_id": item.id,
                "content_title": item.title,
                "priority_label": priority.get("priority_label"),
                "workitem_id": work.id,
                "workitem_title": work.title,
            })

            if len(created_or_updated) >= limit:
                break

        return Response({
            "ok": True,
            "count": len(created_or_updated),
            "items": created_or_updated,
        })