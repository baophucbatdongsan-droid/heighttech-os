from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from django.utils import timezone

from apps.contracts.models import Contract, ContractBookingItem, ContractMilestone, ContractPayment
from apps.work.models import WorkItem


@dataclass(frozen=True)
class ContractHealthScoreResult:
    headline: Dict[str, Any]
    items: List[Dict[str, Any]]


def _health_level(score: int) -> str:
    if score >= 80:
        return "good"
    if score >= 55:
        return "warning"
    return "critical"


def build_contract_health_score(
    *,
    tenant_id: int,
    company_id: Optional[int] = None,
    shop_id: Optional[int] = None,
    project_id: Optional[int] = None,
    limit: int = 10,
) -> ContractHealthScoreResult:
    now = timezone.now()

    contracts = Contract.objects_all.filter(tenant_id=int(tenant_id))
    if company_id:
        contracts = contracts.filter(company_id=int(company_id))
    if shop_id:
        contracts = contracts.filter(contract_shops__shop_id=int(shop_id)).distinct()

    items: List[Dict[str, Any]] = []

    for c in contracts:
        payments_overdue = ContractPayment.objects_all.filter(
            tenant_id=int(tenant_id),
            contract_id=c.id,
            status__in=[ContractPayment.Status.PENDING, ContractPayment.Status.PARTIAL],
            due_at__isnull=False,
            due_at__lt=now,
        ).count()

        milestones_overdue = ContractMilestone.objects_all.filter(
            tenant_id=int(tenant_id),
            contract_id=c.id,
            status__in=[ContractMilestone.Status.TODO, ContractMilestone.Status.DOING],
            due_at__isnull=False,
            due_at__lt=now,
        ).count()

        booking_items = ContractBookingItem.objects_all.filter(
            tenant_id=int(tenant_id),
            contract_id=c.id,
        )

        booking_payout_overdue = booking_items.filter(
            payout_status=ContractBookingItem.PayoutStatus.PENDING,
            payout_due_at__isnull=False,
            payout_due_at__lt=now,
        ).count()

        booking_air_missing = booking_items.filter(
            air_date__isnull=False,
            air_date__lt=now,
        ).filter(
            video_link__isnull=True
        ).count() + booking_items.filter(
            air_date__isnull=False,
            air_date__lt=now,
            video_link="",
        ).count()

        work_qs = WorkItem.objects_all.filter(
            tenant_id=int(tenant_id),
            target_id=c.id,
        )

        contract_work_overdue = work_qs.exclude(
            status__in=[WorkItem.Status.DONE, WorkItem.Status.CANCELLED]
        ).filter(
            due_at__isnull=False,
            due_at__lt=now,
        ).count()

        score = 100
        score -= payments_overdue * 15
        score -= milestones_overdue * 12
        score -= booking_payout_overdue * 10
        score -= booking_air_missing * 8
        score -= contract_work_overdue * 5

        if score < 0:
            score = 0

        level = _health_level(score)

        issues = []
        if payments_overdue:
            issues.append(f"{payments_overdue} payment quá hạn")
        if milestones_overdue:
            issues.append(f"{milestones_overdue} milestone quá hạn")
        if booking_payout_overdue:
            issues.append(f"{booking_payout_overdue} payout quá hạn")
        if booking_air_missing:
            issues.append(f"{booking_air_missing} booking thiếu link")
        if contract_work_overdue:
            issues.append(f"{contract_work_overdue} task quá hạn")

        items.append(
            {
                "contract_id": c.id,
                "contract_code": c.code,
                "contract_name": c.name,
                "contract_type": c.contract_type,
                "company_id": c.company_id,
                "score": score,
                "level": level,
                "issues": issues,
                "payments_overdue": payments_overdue,
                "milestones_overdue": milestones_overdue,
                "booking_payout_overdue": booking_payout_overdue,
                "booking_air_missing": booking_air_missing,
                "contract_work_overdue": contract_work_overdue,
            }
        )

    items.sort(key=lambda x: (int(x.get("score", 0)), x.get("contract_code", "")))
    items = items[: max(1, int(limit or 10))]

    headline = {
        "contract_health_total": len(items),
        "contract_health_good": len([x for x in items if x.get("level") == "good"]),
        "contract_health_warning": len([x for x in items if x.get("level") == "warning"]),
        "contract_health_critical": len([x for x in items if x.get("level") == "critical"]),
    }

    return ContractHealthScoreResult(
        headline=headline,
        items=items,
    )