from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from django.db.models import Q
from django.utils import timezone

from apps.contracts.models import ContractBookingItem, ContractMilestone, ContractPayment
from apps.shops.models import Shop
from apps.work.models import WorkItem


@dataclass(frozen=True)
class ShopRiskRadarResult:
    headline: Dict[str, Any]
    items: List[Dict[str, Any]]


def _risk_level(score: int) -> str:
    if score >= 70:
        return "critical"
    if score >= 35:
        return "warning"
    return "info"


def build_shop_risk_radar(
    *,
    tenant_id: int,
    company_id: Optional[int] = None,
    shop_id: Optional[int] = None,
    project_id: Optional[int] = None,
    limit: int = 8,
) -> ShopRiskRadarResult:
    now = timezone.now()

    shops = Shop.objects_all.filter(tenant_id=int(tenant_id))
    if company_id:
        shops = shops.filter(company_id=int(company_id))
    if shop_id:
        shops = shops.filter(id=int(shop_id))

    items: List[Dict[str, Any]] = []

    for shop in shops:
        sid = int(shop.id)

        payment_overdue = ContractPayment.objects_all.filter(
            tenant_id=int(tenant_id),
            contract__contract_shops__shop_id=sid,
            status__in=[ContractPayment.Status.PENDING, ContractPayment.Status.PARTIAL],
            due_at__isnull=False,
            due_at__lt=now,
        ).distinct().count()

        milestone_overdue = ContractMilestone.objects_all.filter(
            tenant_id=int(tenant_id),
            status__in=[ContractMilestone.Status.TODO, ContractMilestone.Status.DOING],
            due_at__isnull=False,
            due_at__lt=now,
        ).filter(
            Q(shop_id=sid) | Q(contract__contract_shops__shop_id=sid)
        ).distinct().count()

        booking_payout_overdue = ContractBookingItem.objects_all.filter(
            tenant_id=int(tenant_id),
            shop_id=sid,
            payout_status=ContractBookingItem.PayoutStatus.PENDING,
            payout_due_at__isnull=False,
            payout_due_at__lt=now,
        ).count()

        booking_air_missing = ContractBookingItem.objects_all.filter(
            tenant_id=int(tenant_id),
            shop_id=sid,
            air_date__isnull=False,
            air_date__lt=now,
        ).filter(
            Q(video_link__isnull=True) | Q(video_link="")
        ).count()

        work_overdue = WorkItem.objects_all.filter(
            tenant_id=int(tenant_id),
            shop_id=sid,
            due_at__isnull=False,
            due_at__lt=now,
        ).exclude(
            status__in=[WorkItem.Status.DONE, WorkItem.Status.CANCELLED]
        ).count()

        work_urgent = WorkItem.objects_all.filter(
            tenant_id=int(tenant_id),
            shop_id=sid,
            priority=WorkItem.Priority.URGENT,
        ).exclude(
            status__in=[WorkItem.Status.DONE, WorkItem.Status.CANCELLED]
        ).count()

        score = 0
        score += payment_overdue * 10
        score += milestone_overdue * 8
        score += booking_payout_overdue * 7
        score += booking_air_missing * 6
        score += work_overdue * 3
        score += work_urgent * 2

        level = _risk_level(score)

        if score <= 0:
            continue

        items.append(
            {
                "shop_id": sid,
                "shop_name": getattr(shop, "name", "") or f"Shop #{sid}",
                "company_id": getattr(shop, "company_id", None),
                "score": score,
                "level": level,
                "payment_overdue": payment_overdue,
                "milestone_overdue": milestone_overdue,
                "booking_payout_overdue": booking_payout_overdue,
                "booking_air_missing": booking_air_missing,
                "work_overdue": work_overdue,
                "work_urgent": work_urgent,
            }
        )

    items.sort(
        key=lambda x: (
            -int(x.get("score") or 0),
            str(x.get("shop_name") or ""),
        )
    )

    final_items = items[: max(1, int(limit or 8))]

    headline = {
        "shop_risk_total": len(final_items),
        "shop_risk_critical": len([x for x in final_items if x.get("level") == "critical"]),
        "shop_risk_warning": len([x for x in final_items if x.get("level") == "warning"]),
        "shop_risk_info": len([x for x in final_items if x.get("level") == "info"]),
    }

    return ShopRiskRadarResult(
        headline=headline,
        items=final_items,
    )