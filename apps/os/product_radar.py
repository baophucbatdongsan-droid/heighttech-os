from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional

from apps.products.models import Product
from apps.products.models_stats import ProductDailyStat


@dataclass(frozen=True)
class ProductRadarResult:
    headline: Dict[str, Any]
    blocks: Dict[str, Any]


def _to_decimal(v) -> Decimal:
    try:
        return Decimal(str(v or 0))
    except Exception:
        return Decimal("0")


def build_product_radar(
    *,
    tenant_id: int,
    company_id: Optional[int] = None,
    shop_id: Optional[int] = None,
    days: int = 30,
    limit: int = 5,
) -> ProductRadarResult:
    stats = ProductDailyStat.objects_all.select_related("product", "shop").filter(
        tenant_id=int(tenant_id)
    )

    products = Product.objects_all.filter(tenant_id=int(tenant_id))

    if company_id:
        stats = stats.filter(company_id=int(company_id))
        products = products.filter(company_id=int(company_id))

    if shop_id:
        stats = stats.filter(shop_id=int(shop_id))
        products = products.filter(shop_id=int(shop_id))

    product_map: Dict[int, Dict[str, Any]] = {}

    for s in stats:
        pid = int(s.product_id)
        row = product_map.setdefault(
            pid,
            {
                "product_id": pid,
                "sku": getattr(s.product, "sku", "") or "",
                "name": getattr(s.product, "name", "") or "",
                "shop_id": getattr(s, "shop_id", None),
                "units_sold": 0,
                "orders_count": 0,
                "revenue": Decimal("0"),
                "ads_spend": Decimal("0"),
                "booking_cost": Decimal("0"),
                "profit_estimate": Decimal("0"),
                "roas_estimate": Decimal("0"),
                "stock": getattr(s.product, "stock", 0) or 0,
            },
        )

        row["units_sold"] += int(s.units_sold or 0)
        row["orders_count"] += int(s.orders_count or 0)
        row["revenue"] += _to_decimal(s.revenue)
        row["ads_spend"] += _to_decimal(s.ads_spend)
        row["booking_cost"] += _to_decimal(s.booking_cost)
        row["profit_estimate"] += _to_decimal(s.profit_estimate)

    all_rows: List[Dict[str, Any]] = []

    for p in products:
        pid = int(p.id)
        row = product_map.get(pid) or {
            "product_id": pid,
            "sku": p.sku or "",
            "name": p.name or "",
            "shop_id": p.shop_id,
            "units_sold": 0,
            "orders_count": 0,
            "revenue": Decimal("0"),
            "ads_spend": Decimal("0"),
            "booking_cost": Decimal("0"),
            "profit_estimate": Decimal("0"),
            "roas_estimate": Decimal("0"),
            "stock": p.stock or 0,
        }

        ads_spend = _to_decimal(row["ads_spend"])
        revenue = _to_decimal(row["revenue"])
        if ads_spend > 0:
            roas = revenue / ads_spend
        else:
            roas = Decimal("0")

        row["roas_estimate"] = roas
        all_rows.append(row)

    top_sku = sorted(
        all_rows,
        key=lambda x: (-_to_decimal(x["revenue"]), -int(x["units_sold"]), str(x["sku"])),
    )[: max(1, int(limit or 5))]

    low_roas = sorted(
        [x for x in all_rows if _to_decimal(x["ads_spend"]) > 0],
        key=lambda x: (_to_decimal(x["roas_estimate"]), str(x["sku"])),
    )[: max(1, int(limit or 5))]

    losing_sku = sorted(
        [x for x in all_rows if _to_decimal(x["profit_estimate"]) < 0],
        key=lambda x: (_to_decimal(x["profit_estimate"]), str(x["sku"])),
    )[: max(1, int(limit or 5))]

    low_stock = sorted(
        [x for x in all_rows if int(x.get("stock") or 0) < 10],
        key=lambda x: (int(x.get("stock") or 0), str(x["sku"])),
    )[: max(1, int(limit or 5))]

    headline = {
        "product_total": len(all_rows),
        "product_top_count": len(top_sku),
        "product_low_roas_count": len(low_roas),
        "product_losing_count": len(losing_sku),
        "product_low_stock_count": len(low_stock),
    }

    def _serialize(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "product_id": row["product_id"],
            "sku": row["sku"],
            "name": row["name"],
            "shop_id": row["shop_id"],
            "units_sold": row["units_sold"],
            "orders_count": row["orders_count"],
            "revenue": str(_to_decimal(row["revenue"])),
            "ads_spend": str(_to_decimal(row["ads_spend"])),
            "booking_cost": str(_to_decimal(row["booking_cost"])),
            "profit_estimate": str(_to_decimal(row["profit_estimate"])),
            "roas_estimate": str(_to_decimal(row["roas_estimate"])),
            "stock": int(row.get("stock") or 0),
        }

    blocks = {
        "top_sku": [_serialize(x) for x in top_sku],
        "low_roas": [_serialize(x) for x in low_roas],
        "losing_sku": [_serialize(x) for x in losing_sku],
        "low_stock": [_serialize(x) for x in low_stock],
    }

    return ProductRadarResult(
        headline=headline,
        blocks=blocks,
    )