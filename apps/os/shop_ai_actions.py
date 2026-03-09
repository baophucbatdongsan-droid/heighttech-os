from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from apps.os.product_radar import build_product_radar
from apps.os.shop_brain import build_shop_brain
from apps.os.shop_service_timeline import build_shop_service_timeline


@dataclass(frozen=True)
class ShopAIActionResult:
    headline: Dict[str, Any]
    items: List[Dict[str, Any]]


def build_shop_ai_actions(
    *,
    tenant_id: int,
    company_id: Optional[int] = None,
    shop_id: Optional[int] = None,
    limit: int = 8,
) -> ShopAIActionResult:
    items: List[Dict[str, Any]] = []

    shop_brain = build_shop_brain(
        tenant_id=int(tenant_id),
        shop_id=shop_id,
    )

    product_radar = build_product_radar(
        tenant_id=int(tenant_id),
        company_id=company_id,
        shop_id=shop_id,
        days=30,
        limit=5,
    )

    timeline = build_shop_service_timeline(
        tenant_id=int(tenant_id),
        company_id=company_id,
        shop_id=shop_id,
        days=7,
        limit=10,
    )

    # =========================
    # Từ Shop Brain
    # =========================
    for x in (shop_brain.daily_mission or [])[:3]:
        priority = x.get("priority") or "info"
        items.append(
            {
                "kind": "daily_mission",
                "priority": priority,
                "title": x.get("title") or "Daily mission",
                "summary": x.get("summary") or "",
                "action": "Ưu tiên xử lý trong hôm nay và cập nhật trạng thái ngay khi xong.",
            }
        )

    for x in (shop_brain.risks or [])[:2]:
        items.append(
            {
                "kind": "shop_risk",
                "priority": x.get("priority") or "warning",
                "title": x.get("title") or "Rủi ro vận hành",
                "summary": x.get("summary") or "",
                "action": "Rà soát nguyên nhân và giao người xử lý trước khi ảnh hưởng đơn hàng / doanh thu.",
            }
        )

    # =========================
    # Từ Product Radar
    # =========================
    radar_blocks = getattr(product_radar, "blocks", {}) or {}

    for x in (radar_blocks.get("losing_sku") or [])[:2]:
        items.append(
            {
                "kind": "losing_sku",
                "priority": "critical",
                "title": f"SKU đang lỗ: {x.get('sku') or ''}",
                "summary": f"{x.get('name') or ''} • Profit estimate: {x.get('profit_estimate') or '0'}",
                "action": "Kiểm tra lại giá bán, chi phí ads, chi phí booking và cân nhắc dừng đẩy SKU này nếu biên âm kéo dài.",
            }
        )

    for x in (radar_blocks.get("low_roas") or [])[:2]:
        items.append(
            {
                "kind": "low_roas",
                "priority": "warning",
                "title": f"ROAS thấp: {x.get('sku') or ''}",
                "summary": f"{x.get('name') or ''} • ROAS: {x.get('roas_estimate') or '0'}",
                "action": "Tối ưu ads creative / target hoặc chuyển ngân sách sang SKU có hiệu quả tốt hơn.",
            }
        )

    for x in (radar_blocks.get("low_stock") or [])[:2]:
        items.append(
            {
                "kind": "low_stock",
                "priority": "warning",
                "title": f"Sắp hết hàng: {x.get('sku') or ''}",
                "summary": f"{x.get('name') or ''} • Stock: {x.get('stock') or 0}",
                "action": "Chủ động nhập thêm hàng hoặc giảm đẩy traffic để tránh mất đơn vì hết tồn kho.",
            }
        )

    for x in (radar_blocks.get("top_sku") or [])[:2]:
        items.append(
            {
                "kind": "top_sku",
                "priority": "info",
                "title": f"SKU đang bán tốt: {x.get('sku') or ''}",
                "summary": f"{x.get('name') or ''} • Revenue: {x.get('revenue') or '0'} • Units: {x.get('units_sold') or 0}",
                "action": "Có thể tăng ads, đẩy livestream hoặc booking KOC cho SKU này để mở rộng doanh thu.",
            }
        )

    # =========================
    # Từ Service Timeline
    # =========================
    for x in (timeline.items or [])[:3]:
        priority = x.get("priority") or "info"
        items.append(
            {
                "kind": x.get("kind") or "timeline",
                "priority": priority,
                "title": x.get("title") or "Sự kiện dịch vụ sắp tới",
                "summary": x.get("summary") or "",
                "action": "Xác nhận lịch và owner phụ trách trước hạn để tránh trễ mốc dịch vụ.",
            }
        )

    # =========================
    # Sort & limit
    # =========================
    rank = {"critical": 0, "warning": 1, "info": 2}
    items.sort(key=lambda x: (rank.get(x.get("priority") or "info", 9), x.get("title") or ""))

    # bỏ trùng title
    dedup: List[Dict[str, Any]] = []
    seen = set()
    for x in items:
        key = (x.get("kind"), x.get("title"))
        if key in seen:
            continue
        seen.add(key)
        dedup.append(x)

    dedup = dedup[: max(1, int(limit or 8))]

    headline = {
        "shop_ai_actions_total": len(dedup),
        "shop_ai_actions_critical": len([x for x in dedup if x.get("priority") == "critical"]),
        "shop_ai_actions_warning": len([x for x in dedup if x.get("priority") == "warning"]),
        "shop_ai_actions_info": len([x for x in dedup if x.get("priority") == "info"]),
    }

    return ShopAIActionResult(
        headline=headline,
        items=dedup,
    )