from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from apps.shop_services.models import ShopServiceSubscription


@dataclass(frozen=True)
class ShopServicesOverviewResult:
    headline: Dict[str, Any]
    items: List[Dict[str, Any]]


def build_shop_services_overview(
    *,
    tenant_id: int,
    company_id: Optional[int] = None,
    shop_id: Optional[int] = None,
    limit: int = 20,
) -> ShopServicesOverviewResult:
    qs = ShopServiceSubscription.objects_all.select_related(
        "shop",
        "company",
        "contract",
        "owner",
    ).filter(
        tenant_id=int(tenant_id)
    )

    if company_id:
        qs = qs.filter(company_id=int(company_id))

    if shop_id:
        qs = qs.filter(shop_id=int(shop_id))

    items: List[Dict[str, Any]] = []

    for x in qs[: max(1, int(limit or 20))]:
        owner_name = ""
        try:
            owner_name = (
                getattr(x.owner, "full_name", "")
                or getattr(x.owner, "get_full_name", lambda: "")()
                or getattr(x.owner, "username", "")
                or getattr(x.owner, "email", "")
            )
        except Exception:
            owner_name = ""

        items.append(
            {
                "id": x.id,
                "shop_id": x.shop_id,
                "shop_name": getattr(x.shop, "name", "") or f"Shop #{x.shop_id}",
                "service_code": x.service_code,
                "service_name": x.service_name or x.get_service_code_display(),
                "status": x.status,
                "company_id": x.company_id,
                "company_name": getattr(x.company, "name", "") if x.company_id else "",
                "contract_id": x.contract_id,
                "contract_code": getattr(x.contract, "code", "") if x.contract_id else "",
                "contract_name": getattr(x.contract, "name", "") if x.contract_id else "",
                "owner_id": x.owner_id,
                "owner_name": owner_name,
                "start_date": x.start_date.isoformat() if x.start_date else None,
                "end_date": x.end_date.isoformat() if x.end_date else None,
                "note": x.note or "",
            }
        )

    headline = {
        "shop_services_total": len(items),
        "shop_services_active": len([x for x in items if x.get("status") == "active"]),
        "shop_services_paused": len([x for x in items if x.get("status") == "paused"]),
        "shop_services_ended": len([x for x in items if x.get("status") == "ended"]),
    }

    return ShopServicesOverviewResult(
        headline=headline,
        items=items,
    )