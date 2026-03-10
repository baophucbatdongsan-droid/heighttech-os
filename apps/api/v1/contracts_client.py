from __future__ import annotations

from typing import Any, Dict

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.contracts.models import (
    Contract,
    ContractChannelContent,
    ContractChannelDailyMetric,
)


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


def _int_or_none(v):
    try:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        return int(s)
    except Exception:
        return None


def _serialize_content(x: ContractChannelContent) -> Dict[str, Any]:
    metrics = []
    try:
        for m in x.daily_metrics.all()[:30]:
            metrics.append(
                {
                    "id": m.id,
                    "metric_date": m.metric_date.isoformat() if m.metric_date else None,
                    "views": m.views,
                    "likes": m.likes,
                    "comments": m.comments,
                    "shares": m.shares,
                    "saves": m.saves,
                    "orders": m.orders,
                    "revenue": str(m.revenue or 0),
                }
            )
    except Exception:
        pass

    return {
        "id": x.id,
        "contract_id": x.contract_id,
        "shop_id": x.shop_id,
        "title": x.title,
        "script_text": x.script_text or "",
        "content_pillar": x.content_pillar or "",
        "status": x.status,
        "planned_publish_at": x.planned_publish_at.isoformat() if x.planned_publish_at else None,
        "aired_at": x.aired_at.isoformat() if x.aired_at else None,
        "video_link": x.video_link or "",
        "visible_to_client": bool(x.visible_to_client),
        "sort_order": x.sort_order,
        "meta": x.meta or {},
        "daily_metrics": metrics,
    }


class ClientContractChannelProgressApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, contract_id: int):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        shop_id = _int_or_none(request.GET.get("shop_id"))
        if not shop_id:
            return Response({"ok": False, "message": "Thiếu shop_id"}, status=400)

        contract = Contract.objects_all.filter(
            tenant_id=int(tenant_id),
            id=int(contract_id),
        ).first()
        if not contract:
            return Response({"ok": False, "message": "Không tìm thấy hợp đồng"}, status=404)

        contents = (
            ContractChannelContent.objects_all
            .filter(
                tenant_id=int(tenant_id),
                contract_id=contract.id,
                shop_id=int(shop_id),
                visible_to_client=True,
            )
            .prefetch_related("daily_metrics")
            .order_by("sort_order", "id")
        )

        items = [_serialize_content(x) for x in contents]

        headline = {
            "total_contents": len(items),
            "script_ready": len([x for x in items if x["status"] in ("script", "pre_production", "production", "post_production", "scheduled", "aired")]),
            "in_production": len([x for x in items if x["status"] in ("production", "post_production")]),
            "aired": len([x for x in items if x["status"] == "aired"]),
        }

        return Response({
            "ok": True,
            "tenant_id": int(tenant_id),
            "contract_id": contract.id,
            "shop_id": int(shop_id),
            "headline": headline,
            "items": items,
        })