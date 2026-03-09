from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from django.db.models import Q
from django.utils import timezone

from apps.contracts.models import ContractBookingItem, ContractMilestone, ContractPayment
from apps.shop_services.models import ShopServiceSubscription


@dataclass(frozen=True)
class ShopServiceTimelineResult:
    headline: Dict[str, Any]
    items: List[Dict[str, Any]]


def _priority_from_due(dt, now) -> str:
    if not dt:
        return "info"
    if dt < now:
        return "critical"
    if dt <= now + timezone.timedelta(days=3):
        return "warning"
    return "info"


def _service_label(code: str) -> str:
    x = (code or "").strip().lower()
    mapping = {
        "booking": "Booking",
        "channel_build": "Xây kênh",
        "livestream": "Livestream",
        "operations": "Vận hành",
        "ads": "Ads",
        "koc": "KOC",
        "content": "Content",
    }
    return mapping.get(x, code or "Dịch vụ")


def build_shop_service_timeline(
    *,
    tenant_id: int,
    company_id: Optional[int] = None,
    shop_id: Optional[int] = None,
    days: int = 14,
    limit: int = 20,
) -> ShopServiceTimelineResult:
    now = timezone.now()
    until = now + timezone.timedelta(days=max(1, int(days or 14)))

    items: List[Dict[str, Any]] = []

    # =========================
    # Shop services subscription
    # =========================
    svc_qs = ShopServiceSubscription.objects_all.select_related(
        "shop",
        "contract",
        "owner",
    ).filter(
        tenant_id=int(tenant_id),
        status__in=[
            ShopServiceSubscription.Status.ACTIVE,
            ShopServiceSubscription.Status.PAUSED,
        ],
    )

    if company_id:
        svc_qs = svc_qs.filter(company_id=int(company_id))
    if shop_id:
        svc_qs = svc_qs.filter(shop_id=int(shop_id))

    for s in svc_qs:
        label = s.service_name or _service_label(s.service_code)
        if s.start_date:
            start_dt = timezone.make_aware(
                timezone.datetime.combine(s.start_date, timezone.datetime.min.time()),
                timezone.get_current_timezone(),
            )
            if start_dt <= until:
                items.append(
                    {
                        "kind": "shop_service",
                        "title": f"{label} bắt đầu / đang chạy",
                        "summary": f"{getattr(s.shop, 'name', '') or f'Shop #{s.shop_id}'} • trạng thái {s.status}",
                        "event_at": start_dt,
                        "priority": "info" if s.status == "active" else "warning",
                        "service_code": s.service_code,
                        "shop_id": s.shop_id,
                        "shop_name": getattr(s.shop, "name", "") or f"Shop #{s.shop_id}",
                        "contract_code": getattr(s.contract, "code", "") if s.contract_id else "",
                        "owner_name": getattr(s.owner, "username", "") if s.owner_id else "",
                    }
                )

        if s.end_date:
            end_dt = timezone.make_aware(
                timezone.datetime.combine(s.end_date, timezone.datetime.max.time().replace(microsecond=0)),
                timezone.get_current_timezone(),
            )
            if now <= end_dt <= until:
                items.append(
                    {
                        "kind": "shop_service_end",
                        "title": f"{label} sắp kết thúc",
                        "summary": f"{getattr(s.shop, 'name', '') or f'Shop #{s.shop_id}'} • kết thúc ngày {s.end_date.isoformat()}",
                        "event_at": end_dt,
                        "priority": "warning",
                        "service_code": s.service_code,
                        "shop_id": s.shop_id,
                        "shop_name": getattr(s.shop, "name", "") or f"Shop #{s.shop_id}",
                        "contract_code": getattr(s.contract, "code", "") if s.contract_id else "",
                        "owner_name": getattr(s.owner, "username", "") if s.owner_id else "",
                    }
                )

    # =========================
    # Booking air date / payout
    # =========================
    booking_qs = ContractBookingItem.objects_all.select_related(
        "contract",
        "shop",
    ).filter(
        tenant_id=int(tenant_id)
    )

    if company_id:
        booking_qs = booking_qs.filter(contract__company_id=int(company_id))
    if shop_id:
        booking_qs = booking_qs.filter(shop_id=int(shop_id))

    for b in booking_qs:
        if b.air_date and b.air_date <= until:
            items.append(
                {
                    "kind": "booking_air",
                    "title": f"KOC air: {b.koc_name}",
                    "summary": f"{getattr(b.contract, 'code', '')} • {getattr(b.shop, 'name', '') or f'Shop #{b.shop_id}'}",
                    "event_at": b.air_date,
                    "priority": _priority_from_due(b.air_date, now),
                    "shop_id": b.shop_id,
                    "shop_name": getattr(b.shop, "name", "") or f"Shop #{b.shop_id}" if b.shop_id else "",
                    "contract_code": getattr(b.contract, "code", ""),
                    "video_link": b.video_link or "",
                }
            )

        if (
            b.payout_due_at
            and b.payout_status == ContractBookingItem.PayoutStatus.PENDING
            and b.payout_due_at <= until
        ):
            items.append(
                {
                    "kind": "booking_payout",
                    "title": f"Payout KOC: {b.koc_name}",
                    "summary": f"{getattr(b.contract, 'code', '')} • hạn payout",
                    "event_at": b.payout_due_at,
                    "priority": _priority_from_due(b.payout_due_at, now),
                    "shop_id": b.shop_id,
                    "shop_name": getattr(b.shop, "name", "") or f"Shop #{b.shop_id}" if b.shop_id else "",
                    "contract_code": getattr(b.contract, "code", ""),
                    "payout_amount": str(b.payout_amount or 0),
                }
            )

    # =========================
    # Milestone
    # =========================
    milestone_qs = ContractMilestone.objects_all.select_related(
        "contract",
        "shop",
    ).filter(
        tenant_id=int(tenant_id),
        due_at__isnull=False,
        due_at__lte=until,
        status__in=[ContractMilestone.Status.TODO, ContractMilestone.Status.DOING],
    )

    if company_id:
        milestone_qs = milestone_qs.filter(contract__company_id=int(company_id))
    if shop_id:
        milestone_qs = milestone_qs.filter(
            Q(shop_id=int(shop_id)) | Q(contract__contract_shops__shop_id=int(shop_id))
        ).distinct()

    for m in milestone_qs:
        items.append(
            {
                "kind": "milestone",
                "title": f"Milestone: {m.title}",
                "summary": f"{getattr(m.contract, 'code', '')} • {getattr(m.shop, 'name', '') or ''}",
                "event_at": m.due_at,
                "priority": _priority_from_due(m.due_at, now),
                "shop_id": m.shop_id,
                "shop_name": getattr(m.shop, "name", "") or "",
                "contract_code": getattr(m.contract, "code", ""),
            }
        )

    # =========================
    # Contract payment
    # =========================
    payment_qs = ContractPayment.objects_all.select_related(
        "contract",
    ).filter(
        tenant_id=int(tenant_id),
        due_at__isnull=False,
        due_at__lte=until,
        status__in=[ContractPayment.Status.PENDING, ContractPayment.Status.PARTIAL],
    )

    if company_id:
        payment_qs = payment_qs.filter(contract__company_id=int(company_id))
    if shop_id:
        payment_qs = payment_qs.filter(contract__contract_shops__shop_id=int(shop_id)).distinct()

    for p in payment_qs:
        items.append(
            {
                "kind": "contract_payment",
                "title": f"Payment: {p.title}",
                "summary": f"{getattr(p.contract, 'code', '')} • đến hạn thanh toán",
                "event_at": p.due_at,
                "priority": _priority_from_due(p.due_at, now),
                "shop_id": shop_id,
                "shop_name": "",
                "contract_code": getattr(p.contract, "code", ""),
                "amount": str(p.amount or 0),
            }
        )

    items.sort(
        key=lambda x: (
            x.get("event_at") or now,
            x.get("title") or "",
        )
    )

    final_items = items[: max(1, int(limit or 20))]

    headline = {
        "shop_service_timeline_total": len(final_items),
        "shop_service_timeline_critical": len([x for x in final_items if x.get("priority") == "critical"]),
        "shop_service_timeline_warning": len([x for x in final_items if x.get("priority") == "warning"]),
        "shop_service_timeline_info": len([x for x in final_items if x.get("priority") == "info"]),
    }

    def _serialize(x: Dict[str, Any]) -> Dict[str, Any]:
        y = dict(x)
        if y.get("event_at"):
            y["event_at"] = y["event_at"].isoformat()
        return y

    return ShopServiceTimelineResult(
        headline=headline,
        items=[_serialize(x) for x in final_items],
    )