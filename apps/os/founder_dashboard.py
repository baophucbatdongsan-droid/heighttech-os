from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional

from django.utils import timezone

from apps.contracts.models import Contract, ContractBookingItem, ContractPayment
from apps.work.models import WorkItem


def _to_decimal(v) -> Decimal:
    try:
        return Decimal(str(v or 0))
    except Exception:
        return Decimal("0")


def _money_str(v: Decimal) -> str:
    try:
        return f"{int(v):,}".replace(",", ".")
    except Exception:
        return str(v)


@dataclass(frozen=True)
class FounderDashboardResult:
    headline: Dict[str, Any]
    blocks: Dict[str, Any]


def build_founder_dashboard(
    *,
    tenant_id: int,
    company_id: Optional[int] = None,
    shop_id: Optional[int] = None,
    project_id: Optional[int] = None,
) -> FounderDashboardResult:
    now = timezone.now()

    contracts = Contract.objects_all.filter(tenant_id=int(tenant_id))
    if company_id:
        contracts = contracts.filter(company_id=int(company_id))
    if shop_id:
        contracts = contracts.filter(contract_shops__shop_id=int(shop_id)).distinct()

    contract_ids = list(contracts.values_list("id", flat=True))

    payments = ContractPayment.objects_all.filter(
        tenant_id=int(tenant_id),
        contract_id__in=contract_ids,
    )

    receivable_pending = payments.filter(
        status__in=[ContractPayment.Status.PENDING, ContractPayment.Status.PARTIAL]
    )

    receivable_overdue_qs = receivable_pending.filter(due_at__isnull=False, due_at__lt=now)
    receivable_due_soon_qs = receivable_pending.filter(
        due_at__isnull=False,
        due_at__gte=now,
        due_at__lte=now + timezone.timedelta(days=7),
    )

    total_contract_value = sum((_to_decimal(x.total_value) for x in contracts), Decimal("0"))
    receivable_pending_total = sum((_to_decimal(x.amount) for x in receivable_pending), Decimal("0"))
    receivable_overdue_total = sum((_to_decimal(x.amount) for x in receivable_overdue_qs), Decimal("0"))
    receivable_due_soon_total = sum((_to_decimal(x.amount) for x in receivable_due_soon_qs), Decimal("0"))

    booking_items = ContractBookingItem.objects_all.filter(
        tenant_id=int(tenant_id),
        contract_id__in=contract_ids,
    )
    if shop_id:
        booking_items = booking_items.filter(shop_id=int(shop_id))

    payout_pending_qs = booking_items.filter(
        payout_status=ContractBookingItem.PayoutStatus.PENDING
    )
    payout_due_soon_qs = payout_pending_qs.filter(
        payout_due_at__isnull=False,
        payout_due_at__gte=now,
        payout_due_at__lte=now + timezone.timedelta(days=7),
    )
    payout_overdue_qs = payout_pending_qs.filter(
        payout_due_at__isnull=False,
        payout_due_at__lt=now,
    )

    payout_pending_total = sum((_to_decimal(x.payout_amount) for x in payout_pending_qs), Decimal("0"))
    payout_due_soon_total = sum((_to_decimal(x.payout_amount) for x in payout_due_soon_qs), Decimal("0"))
    payout_overdue_total = sum((_to_decimal(x.payout_amount) for x in payout_overdue_qs), Decimal("0"))

    work_qs = WorkItem.objects_all.filter(tenant_id=int(tenant_id))
    if company_id:
        work_qs = work_qs.filter(company_id=int(company_id))
    if shop_id:
        work_qs = work_qs.filter(shop_id=int(shop_id))
    if project_id:
        work_qs = work_qs.filter(project_id=int(project_id))

    backlog_qs = work_qs.exclude(status__in=[WorkItem.Status.DONE, WorkItem.Status.CANCELLED])
    backlog_total = backlog_qs.count()
    backlog_overdue = backlog_qs.filter(due_at__isnull=False, due_at__lt=now).count()
    backlog_urgent = backlog_qs.filter(priority=WorkItem.Priority.URGENT).count()

    risk_score = 0
    risk_score += min(40, receivable_overdue_qs.count() * 5)
    risk_score += min(30, payout_overdue_qs.count() * 5)
    risk_score += min(20, backlog_overdue * 2)
    risk_score += min(10, backlog_urgent * 1)

    if risk_score >= 70:
        risk_level = "critical"
    elif risk_score >= 40:
        risk_level = "warning"
    else:
        risk_level = "info"

    headline = {
        "founder_total_contract_value": str(total_contract_value),
        "founder_receivable_pending_total": str(receivable_pending_total),
        "founder_payout_pending_total": str(payout_pending_total),
        "founder_backlog_total": backlog_total,
        "founder_risk_score": risk_score,
        "founder_risk_level": risk_level,
    }

    blocks = {
        "summary_cards": [
            {
                "key": "contract_value",
                "label": "Tổng giá trị hợp đồng",
                "value": _money_str(total_contract_value),
                "unit": "đ",
            },
            {
                "key": "receivable_pending",
                "label": "Công nợ chờ thu",
                "value": _money_str(receivable_pending_total),
                "unit": "đ",
            },
            {
                "key": "payout_pending",
                "label": "Payout KOC chờ trả",
                "value": _money_str(payout_pending_total),
                "unit": "đ",
            },
            {
                "key": "backlog_total",
                "label": "Backlog task mở",
                "value": str(backlog_total),
                "unit": "task",
            },
        ],
        "finance": {
            "receivable_overdue_total": _money_str(receivable_overdue_total),
            "receivable_due_soon_total": _money_str(receivable_due_soon_total),
            "payout_overdue_total": _money_str(payout_overdue_total),
            "payout_due_soon_total": _money_str(payout_due_soon_total),
        },
        "risk": {
            "score": risk_score,
            "level": risk_level,
            "backlog_overdue": backlog_overdue,
            "backlog_urgent": backlog_urgent,
            "receivable_overdue_count": receivable_overdue_qs.count(),
            "payout_overdue_count": payout_overdue_qs.count(),
        },
    }

    return FounderDashboardResult(headline=headline, blocks=blocks)