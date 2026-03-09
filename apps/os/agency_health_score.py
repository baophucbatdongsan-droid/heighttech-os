from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from django.utils import timezone

from apps.contracts.models import ContractPayment, ContractMilestone
from apps.work.models import WorkItem


@dataclass(frozen=True)
class AgencyHealthScoreResult:
    score: int
    blocks: Dict


def _score_from_ratio(bad: int, total: int) -> int:
    if total <= 0:
        return 100
    ratio = bad / total
    score = int(100 - ratio * 100)
    if score < 0:
        score = 0
    return score


def build_agency_health_score(
    *,
    tenant_id: int,
    company_id=None,
    shop_id=None,
    project_id=None,
):
    now = timezone.now()

    payments = ContractPayment.objects_all.filter(
        tenant_id=int(tenant_id)
    )

    if company_id:
        payments = payments.filter(contract__company_id=int(company_id))

    overdue_payments = payments.filter(
        status__in=[ContractPayment.Status.PENDING, ContractPayment.Status.PARTIAL],
        due_at__lt=now,
    ).count()

    total_payments = payments.count()

    finance_score = _score_from_ratio(overdue_payments, total_payments)

    milestones = ContractMilestone.objects_all.filter(
        tenant_id=int(tenant_id)
    )

    overdue_milestones = milestones.filter(
        status__in=[ContractMilestone.Status.TODO, ContractMilestone.Status.DOING],
        due_at__lt=now,
    ).count()

    delivery_score = _score_from_ratio(overdue_milestones, milestones.count())

    works = WorkItem.objects_all.filter(
        tenant_id=int(tenant_id)
    )

    overdue_work = works.exclude(
        status__in=[WorkItem.Status.DONE, WorkItem.Status.CANCELLED]
    ).filter(
        due_at__lt=now
    ).count()

    operations_score = _score_from_ratio(overdue_work, works.count())

    contract_score = int((finance_score + delivery_score) / 2)

    score = int(
        finance_score * 0.3
        + delivery_score * 0.3
        + contract_score * 0.2
        + operations_score * 0.2
    )

    blocks = {
        "finance": finance_score,
        "delivery": delivery_score,
        "contracts": contract_score,
        "operations": operations_score,
    }

    return AgencyHealthScoreResult(
        score=score,
        blocks=blocks,
    )