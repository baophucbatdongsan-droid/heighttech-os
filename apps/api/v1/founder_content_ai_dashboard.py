from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.contracts.models import ContractChannelContent
from apps.contracts.services_content_ai import score_content


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


def _to_decimal(v):
    try:
        return Decimal(str(v or 0))
    except Exception:
        return Decimal("0")


class FounderContentAiDashboardApi(APIView):
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

        content_rows = []
        shop_map = defaultdict(lambda: {
            "shop_id": None,
            "shop_name": "",
            "total_contents": 0,
            "aired_contents": 0,
            "total_views": 0,
            "total_orders": 0,
            "total_revenue": Decimal("0"),
            "avg_health_score": 0,
            "content_scores": [],
        })

        for item in contents:
            metrics = []
            total_views = 0
            total_orders = 0
            total_revenue = Decimal("0")

            try:
                for m in item.daily_metrics.all().order_by("-metric_date")[:14]:
                    row = {
                        "views": m.views,
                        "likes": m.likes,
                        "comments": m.comments,
                        "shares": m.shares,
                        "orders": m.orders,
                        "revenue": str(m.revenue or 0),
                    }
                    metrics.append(row)
                    total_views += int(m.views or 0)
                    total_orders += int(m.orders or 0)
                    total_revenue += _to_decimal(m.revenue)
            except Exception:
                pass

            ai = score_content(metrics)

            row = {
                "content_id": item.id,
                "title": item.title,
                "status": item.status,
                "shop_id": item.shop_id,
                "shop_name": getattr(getattr(item, "shop", None), "name", "") if getattr(item, "shop", None) else "",
                "contract_id": item.contract_id,
                "contract_name": getattr(getattr(item, "contract", None), "name", "") if getattr(item, "contract", None) else "",
                "video_link": item.video_link or "",
                "views_14d": total_views,
                "orders_14d": total_orders,
                "revenue_14d": str(total_revenue),
                "ai": ai,
            }
            content_rows.append(row)

            shop_key = item.shop_id or 0
            shop_map[shop_key]["shop_id"] = item.shop_id
            shop_map[shop_key]["shop_name"] = getattr(getattr(item, "shop", None), "name", "") if getattr(item, "shop", None) else "Chưa gắn shop"
            shop_map[shop_key]["total_contents"] += 1
            if item.status == "aired":
                shop_map[shop_key]["aired_contents"] += 1
            shop_map[shop_key]["total_views"] += total_views
            shop_map[shop_key]["total_orders"] += total_orders
            shop_map[shop_key]["total_revenue"] += total_revenue
            shop_map[shop_key]["content_scores"].append(int(ai.get("health_score", 0)))

        strong_contents = sorted(
            content_rows,
            key=lambda x: (
                int(x["ai"].get("health_score", 0)),
                int(x["views_14d"]),
                int(x["orders_14d"]),
            ),
            reverse=True,
        )[:10]

        weak_contents = sorted(
            content_rows,
            key=lambda x: (
                int(x["ai"].get("health_score", 0)),
                int(x["views_14d"]),
            )
        )[:10]

        shop_rows = []
        for _, s in shop_map.items():
            scores = s["content_scores"] or [0]
            avg_score = int(sum(scores) / max(len(scores), 1))
            s["avg_health_score"] = avg_score
            s["total_revenue"] = str(s["total_revenue"])

            if avg_score >= 75:
                s["shop_label"] = "strong"
                s["recommendation"] = "Shop đang có content tốt. Nên nhân bản format thắng và tăng tốc lịch đăng."
            elif avg_score >= 50:
                s["shop_label"] = "normal"
                s["recommendation"] = "Shop ổn nhưng chưa bật mạnh. Cần tối ưu hook và tăng tỷ lệ air đều."
            else:
                s["shop_label"] = "risk"
                s["recommendation"] = "Shop đang yếu. Cần review concept, kịch bản và tiến độ sản xuất."
            del s["content_scores"]
            shop_rows.append(s)

        shop_rows = sorted(
            shop_rows,
            key=lambda x: (int(x["avg_health_score"]), int(x["total_views"])),
            reverse=True,
        )

        headline = {
            "total_contents": len(content_rows),
            "total_shops": len(shop_rows),
            "boostable_contents": len([x for x in content_rows if x["ai"].get("label") == "boostable"]),
            "weak_contents": len([x for x in content_rows if x["ai"].get("label") in ("weak", "weak-conversion", "no-data")]),
        }

        return Response({
            "ok": True,
            "tenant_id": int(tenant_id),
            "headline": headline,
            "top_contents": strong_contents,
            "weak_contents": weak_contents,
            "shops": shop_rows,
        })