from __future__ import annotations
from collections import defaultdict
from typing import Any, Dict, List
from django.utils import timezone
from datetime import timedelta

from apps.contracts.models import (
    Contract,
    ContractPayment,
    ContractMilestone,
    ContractBookingItem,
)


LOOKAHEAD_DAYS = 14


def build_contract_radar(*, tenant_id: int, company_id=None, shop_id=None) -> Dict[str, Any]:
    now = timezone.now()
    lookahead = now + timedelta(days=LOOKAHEAD_DAYS)

    shops: Dict[int, Dict] = {}

    contracts = Contract.objects.filter(tenant_id=tenant_id)

    if company_id:
        contracts = contracts.filter(company_id=company_id)

    for c in contracts:
        shop_ids = list(
            c.contract_shops.values_list("shop_id", flat=True)
        )

        for sid in shop_ids:
            if shop_id and sid != shop_id:
                continue

            if sid not in shops:
                shops[sid] = {
                    "shop_id": sid,
                    "contracts": defaultdict(list),
                }

            radar_items = []

            payments = ContractPayment.objects.filter(
                contract=c,
                due_at__lte=lookahead
            )

            for p in payments:
                if p.due_at and p.due_at < now:
                    radar_items.append({
                        "type": "payment_overdue",
                        "title": f"Payment quá hạn",
                        "due_at": p.due_at,
                        "priority": "critical"
                    })
                else:
                    radar_items.append({
                        "type": "payment_due",
                        "title": f"Payment sắp đến hạn",
                        "due_at": p.due_at,
                        "priority": "warning"
                    })

            milestones = ContractMilestone.objects.filter(
                contract=c,
                due_at__lte=lookahead
            )

            for m in milestones:
                radar_items.append({
                    "type": "milestone",
                    "title": f"Milestone: {m.title}",
                    "due_at": m.due_at,
                    "priority": "warning"
                })

            bookings = ContractBookingItem.objects.filter(
                contract=c,
                air_date__lte=lookahead
            )

            for b in bookings:
                radar_items.append({
                    "type": "booking_air",
                    "title": f"KOC {b.koc_name} sắp air",
                    "due_at": b.air_date,
                    "priority": "info"
                })

            if radar_items:
                shops[sid]["contracts"][c.code].extend(radar_items)

    result = []

    for sid, data in shops.items():
        result.append({
            "shop_id": sid,
            "contracts": [
                {
                    "contract_code": code,
                    "items": items
                }
                for code, items in data["contracts"].items()
            ]
        })

    return {
        "shops": result,
        "count": len(result)
    }