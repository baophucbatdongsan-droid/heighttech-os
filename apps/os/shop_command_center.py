from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from apps.os.product_radar import build_product_radar
from apps.os.shop_service_timeline import build_shop_service_timeline


@dataclass(frozen=True)
class ShopCommandCenterResult:
    headline: Dict[str, Any]
    missions: List[Dict[str, Any]]


def build_shop_command_center(
    *,
    tenant_id: int,
    company_id: Optional[int] = None,
    shop_id: Optional[int] = None,
) -> ShopCommandCenterResult:

    missions: List[Dict[str, Any]] = []

    radar = build_product_radar(
        tenant_id=tenant_id,
        company_id=company_id,
        shop_id=shop_id,
        limit=3,
    )

    blocks = getattr(radar, "blocks", {}) or {}

    # SKU lỗ
    for x in blocks.get("losing_sku", [])[:2]:
        missions.append(
            {
                "kind": "losing_sku",
                "priority": "critical",
                "title": f"SKU đang lỗ: {x.get('sku')}",
                "summary": f"Lợi nhuận: {x.get('profit_estimate')} • kiểm tra giá / ads / chi phí",
            }
        )

    # ROAS thấp
    for x in blocks.get("low_roas", [])[:2]:
        missions.append(
            {
                "kind": "low_roas",
                "priority": "warning",
                "title": f"ROAS thấp: {x.get('sku')}",
                "summary": f"ROAS: {x.get('roas_estimate')} • cân nhắc tối ưu ads",
            }
        )

    # Tồn kho thấp
    for x in blocks.get("low_stock", [])[:2]:
        missions.append(
            {
                "kind": "low_stock",
                "priority": "warning",
                "title": f"Sắp hết hàng: {x.get('sku')}",
                "summary": f"Tồn kho: {x.get('stock')} • cần nhập thêm",
            }
        )

    timeline = build_shop_service_timeline(
        tenant_id=tenant_id,
        company_id=company_id,
        shop_id=shop_id,
        days=3,
        limit=5,
    )

    for x in (timeline.items or [])[:2]:
        missions.append(
            {
                "kind": "timeline",
                "priority": x.get("priority") or "info",
                "title": x.get("title"),
                "summary": x.get("summary"),
            }
        )

    missions = sorted(
        missions,
        key=lambda x: (
            {"critical": 0, "warning": 1, "info": 2}.get(x.get("priority"), 3),
            x.get("title") or "",
        ),
    )[:6]

    headline = {
        "shop_command_missions": len(missions),
        "shop_command_critical": len([x for x in missions if x["priority"] == "critical"]),
        "shop_command_warning": len([x for x in missions if x["priority"] == "warning"]),
    }

    return ShopCommandCenterResult(
        headline=headline,
        missions=missions,
    )