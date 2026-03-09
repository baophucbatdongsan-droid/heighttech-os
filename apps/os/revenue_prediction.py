from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional

from django.utils import timezone

from apps.contracts.models import ContractPayment


def _d(v):
    try:
        return Decimal(str(v or 0))
    except Exception:
        return Decimal("0")


@dataclass(frozen=True)
class RevenuePredictionResult:
    headline: Dict
    items: List[Dict]


def build_revenue_prediction(
    *,
    tenant_id: int,
    company_id: Optional[int] = None,
    shop_id: Optional[int] = None,
):

    now = timezone.now()
    next_30 = now + timezone.timedelta(days=30)

    qs = ContractPayment.objects_all.filter(
        tenant_id=int(tenant_id),
        due_at__isnull=False,
        due_at__lte=next_30,
    )

    if company_id:
        qs = qs.filter(contract__company_id=int(company_id))

    if shop_id:
        qs = qs.filter(contract__contract_shops__shop_id=int(shop_id)).distinct()

    expected = Decimal("0")
    high_conf = Decimal("0")
    risk = Decimal("0")

    for p in qs:

        amt = _d(p.amount)
        expected += amt

        if p.status == "paid":
            high_conf += amt
        elif p.status == "partial":
            high_conf += amt * Decimal("0.7")
        else:
            risk += amt

    headline = {
        "revenue_expected_30d": str(expected),
        "revenue_high_confidence": str(high_conf),
        "revenue_risk": str(risk),
    }

    items = [
        {
            "label": "Expected Revenue (30d)",
            "value": str(expected),
        },
        {
            "label": "High Confidence",
            "value": str(high_conf),
        },
        {
            "label": "Risk Revenue",
            "value": str(risk),
        },
    ]

    return RevenuePredictionResult(
        headline=headline,
        items=items,
    )