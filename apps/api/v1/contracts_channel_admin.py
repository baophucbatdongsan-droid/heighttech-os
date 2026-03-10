from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.contracts.models import (
    Contract,
    ContractChannelContent,
    ContractChannelDailyMetric,
)
from apps.shops.models import Shop


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
        return int(tid)

    tid = getattr(request, "tenant_id", None)
    if tid:
        return int(tid)

    return None


def _int(v):
    try:
        return int(v)
    except:
        return None


def _dec(v):
    try:
        return Decimal(str(v))
    except:
        return Decimal("0")


def _serialize_content(x: ContractChannelContent) -> Dict[str, Any]:
    return {
        "id": x.id,
        "title": x.title,
        "status": x.status,
        "script_text": x.script_text or "",
        "content_pillar": x.content_pillar or "",
        "planned_publish_at": x.planned_publish_at.isoformat() if x.planned_publish_at else None,
        "aired_at": x.aired_at.isoformat() if x.aired_at else None,
        "video_link": x.video_link or "",
        "visible_to_client": x.visible_to_client,
        "shop_id": x.shop_id,
        "sort_order": x.sort_order,
    }


class ChannelContentListApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, contract_id: int):
        tenant_id = _tenant_id_from_request(request)

        qs = (
            ContractChannelContent.objects_all
            .filter(
                tenant_id=tenant_id,
                contract_id=contract_id,
            )
            .order_by("sort_order", "id")
        )

        items = [_serialize_content(x) for x in qs]

        return Response({
            "ok": True,
            "items": items
        })


class ChannelContentCreateApi(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, contract_id: int):
        tenant_id = _tenant_id_from_request(request)

        data = request.data

        contract = Contract.objects_all.filter(
            id=contract_id,
            tenant_id=tenant_id
        ).first()

        if not contract:
            return Response({"ok": False, "message": "contract không tồn tại"}, status=400)

        shop_id = _int(data.get("shop_id"))

        shop = None
        if shop_id:
            shop = Shop.objects_all.filter(
                id=shop_id,
                tenant_id=tenant_id
            ).first()

        item = ContractChannelContent.objects_all.create(
            tenant_id=tenant_id,
            contract=contract,
            company_id=contract.company_id,
            shop=shop,
            title=data.get("title", ""),
            script_text=data.get("script_text", ""),
            content_pillar=data.get("content_pillar", ""),
            status=data.get("status", "idea"),
            planned_publish_at=data.get("planned_publish_at"),
            visible_to_client=bool(data.get("visible_to_client", True)),
            sort_order=_int(data.get("sort_order")) or 1,
        )

        return Response({
            "ok": True,
            "item": _serialize_content(item)
        })


class ChannelContentUpdateApi(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, content_id: int):
        tenant_id = _tenant_id_from_request(request)

        item = ContractChannelContent.objects_all.filter(
            id=content_id,
            tenant_id=tenant_id
        ).first()

        if not item:
            return Response({"ok": False, "message": "content không tồn tại"}, status=404)

        data = request.data

        item.title = data.get("title", item.title)
        item.script_text = data.get("script_text", item.script_text)
        item.content_pillar = data.get("content_pillar", item.content_pillar)
        item.status = data.get("status", item.status)
        item.video_link = data.get("video_link", item.video_link)
        item.visible_to_client = bool(data.get("visible_to_client", item.visible_to_client))

        if data.get("aired"):
            item.status = "aired"
            item.aired_at = timezone.now()

        item.save()

        return Response({
            "ok": True,
            "item": _serialize_content(item)
        })


class ChannelContentMetricUpdateApi(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, content_id: int):
        tenant_id = _tenant_id_from_request(request)

        content = ContractChannelContent.objects_all.filter(
            id=content_id,
            tenant_id=tenant_id
        ).first()

        if not content:
            return Response({"ok": False, "message": "content không tồn tại"}, status=404)

        data = request.data

        metric_date = data.get("metric_date") or str(date.today())

        metric, _ = ContractChannelDailyMetric.objects_all.get_or_create(
            tenant_id=tenant_id,
            content=content,
            metric_date=metric_date
        )

        metric.views = _int(data.get("views")) or metric.views
        metric.likes = _int(data.get("likes")) or metric.likes
        metric.comments = _int(data.get("comments")) or metric.comments
        metric.shares = _int(data.get("shares")) or metric.shares
        metric.orders = _int(data.get("orders")) or metric.orders
        metric.revenue = _dec(data.get("revenue")) or metric.revenue

        metric.save()

        return Response({
            "ok": True
        })