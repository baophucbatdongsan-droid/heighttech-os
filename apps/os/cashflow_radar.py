from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional

from django.utils import timezone

from apps.contracts.models import ContractBookingItem, ContractPayment


def _to_decimal(v):
    try:
        return Decimal(str(v or 0))
    except Exception:
        return Decimal("0")


@dataclass(frozen=True)
class CashflowRadarResult:
    headline: Dict
    items: List[Dict]


def build_cashflow_radar(
    *,
    tenant_id: int,
    company_id: Optional[int] = None,
    shop_id: Optional[int] = None,
):

    now = timezone.now()
    next_30 = now + timezone.timedelta(days=30)

    payments = ContractPayment.objects_all.filter(
        tenant_id=int(tenant_id),
        due_at__isnull=False,
        due_at__lte=next_30,
    )

    if company_id:
        payments = payments.filter(contract__company_id=int(company_id))

    if shop_id:
        payments = payments.filter(contract__contract_shops__shop_id=int(shop_id)).distinct()

    revenue_expected = Decimal("0")
    revenue_overdue = Decimal("0")

    for p in payments:
        amt = _to_decimal(p.amount)
        revenue_expected += amt

        if p.due_at and p.due_at < now:
            revenue_overdue += amt

    payouts = ContractBookingItem.objects_all.filter(
        tenant_id=int(tenant_id),
        payout_due_at__isnull=False,
        payout_due_at__lte=next_30,
    )

    if company_id:
        payouts = payouts.filter(contract__company_id=int(company_id))

    if shop_id:
        payouts = payouts.filter(shop_id=int(shop_id))

    payout_expected = Decimal("0")
    payout_overdue = Decimal("0")

    for p in payouts:
        amt = _to_decimal(p.payout_amount)
        payout_expected += amt

        if p.payout_due_at and p.payout_due_at < now:
            payout_overdue += amt

    margin = revenue_expected - payout_expected

    if margin < 0:
        level = "critical"
    elif margin < revenue_expected * Decimal("0.2"):
        level = "warning"
    else:
        level = "info"

    headline = {
        "cashflow_expected_revenue": str(revenue_expected),
        "cashflow_expected_payout": str(payout_expected),
        "cashflow_margin": str(margin),
        "cashflow_level": level,
    }

    items = [
        {
            "label": "Expected Revenue (30d)",
            "value": str(revenue_expected),
        },
        {
            "label": "Expected Payout (30d)",
            "value": str(payout_expected),
        },
        {
            "label": "Net Margin",
            "value": str(margin),
            "level": level,
        },
        {
            "label": "Overdue Receivable",
            "value": str(revenue_overdue),
        },
        {
            "label": "Overdue Payout",
            "value": str(payout_overdue),
        },
    ]

    return CashflowRadarResult(
        headline=headline,
        items=items,
    )