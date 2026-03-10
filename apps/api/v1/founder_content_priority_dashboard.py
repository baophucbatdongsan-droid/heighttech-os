from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.contracts.models import ContractChannelContent
from apps.contracts.services_content_ai import score_content
from apps.contracts.services_content_priority import decide_priority


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


class FounderContentPriorityDashboardApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        contents = (
            ContractChannelContent.objects_all
            .filter(tenant_id=int(tenant_id))
            .prefetch_related("daily_metrics", "shop", "contract")
            .order_by("-id")[:300]
        )

        rows = []
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

            base_row = {
                "content_id": item.id,
                "title": item.title,
                "status": item.status,
                "shop_id": item.shop_id,
                "shop_name": getattr(getattr(item, "shop", None), "name", "") if getattr(item, "shop", None) else "Chưa gắn shop",
                "contract_id": item.contract_id,
                "contract_name": getattr(getattr(item, "contract", None), "name", "") if getattr(item, "contract", None) else "",
                "views_14d": total_views,
                "orders_14d": total_orders,
                "revenue_14d": total_revenue,
                "video_link": item.video_link or "",
                "ai": ai,
            }

            priority = decide_priority(base_row)
            base_row["priority"] = priority
            rows.append(base_row)

        rows = sorted(
            rows,
            key=lambda x: (
                int((x.get("priority") or {}).get("priority_score", 0)),
                int((x.get("ai") or {}).get("health_score", 0)),
                int(x.get("views_14d", 0)),
            ),
            reverse=True,
        )

        headline = {
            "total_contents": len(rows),
            "scale_now": len([x for x in rows if x["priority"]["priority_label"] == "scale_now"]),
            "produce_now": len([x for x in rows if x["priority"]["priority_label"] == "produce_now"]),
            "fix_now": len([x for x in rows if x["priority"]["priority_label"] == "fix_now"]),
        }

        return Response({
            "ok": True,
            "tenant_id": int(tenant_id),
            "headline": headline,
            "items": rows[:50],
        })