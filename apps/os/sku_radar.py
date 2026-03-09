from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional

from apps.products.models import Product
from apps.products.models_stats import ProductDailyStat


@dataclass(frozen=True)
class SKURadarResult:
    headline: Dict[str, Any]
    blocks: Dict[str, Any]


def _to_decimal(v) -> Decimal:
    try:
        return Decimal(str(v or 0))
    except Exception:
        return Decimal("0")


def build_sku_radar(
    *,
    tenant_id: int,
    company_id: Optional[int] = None,
    shop_id: Optional[int] = None,
    limit: int = 5,
) -> SKURadarResult:
    stats = ProductDailyStat.objects_all.select_related("product").filter(
        tenant_id=int(tenant_id)
    )
    products = Product.objects_all.filter(tenant_id=int(tenant_id))

    if company_id:
        stats = stats.filter(company_id=int(company_id))
        products = products.filter(company_id=int(company_id))

    if shop_id:
        stats = stats.filter(shop_id=int(shop_id))
        products = products.filter(shop_id=int(shop_id))

    radar: Dict[int, Dict[str, Any]] = {}

    for s in stats:
        pid = int(s.product_id)
        row = radar.setdefault(
            pid,
            {
                "product_id": pid,
                "sku": getattr(s.product, "sku", "") or "",
                "name": getattr(s.product, "name", "") or "",
                "stock": int(getattr(s.product, "stock", 0) or 0),
                "units_sold": 0,
                "orders_count": 0,
                "revenue": Decimal("0"),
                "ads_spend": Decimal("0"),
                "profit_estimate": Decimal("0"),
                "roas_estimate": Decimal("0"),
            },
        )

        row["units_sold"] += int(s.units_sold or 0)
        row["orders_count"] += int(s.orders_count or 0)
        row["revenue"] += _to_decimal(s.revenue)
        row["ads_spend"] += _to_decimal(s.ads_spend)
        row["profit_estimate"] += _to_decimal(s.profit_estimate)

    rows: List[Dict[str, Any]] = []

    for p in products:
        row = radar.get(int(p.id)) or {
            "product_id": int(p.id),
            "sku": p.sku or "",
            "name": p.name or "",
            "stock": int(p.stock or 0),
            "units_sold": 0,
            "orders_count": 0,
            "revenue": Decimal("0"),
            "ads_spend": Decimal("0"),
            "profit_estimate": Decimal("0"),
            "roas_estimate": Decimal("0"),
        }

        revenue = _to_decimal(row["revenue"])
        ads = _to_decimal(row["ads_spend"])
        row["roas_estimate"] = (revenue / ads) if ads > 0 else Decimal("0")

        rows.append(row)

    top_selling = sorted(
        rows,
        key=lambda x: (-_to_decimal(x["revenue"]), -int(x["units_sold"]), str(x["sku"])),
    )[: max(1, int(limit or 5))]

    low_roas = sorted(
        [x for x in rows if _to_decimal(x["ads_spend"]) > 0],
        key=lambda x: (_to_decimal(x["roas_estimate"]), str(x["sku"])),
    )[: max(1, int(limit or 5))]

    losing_sku = sorted(
        [x for x in rows if _to_decimal(x["profit_estimate"]) < 0],
        key=lambda x: (_to_decimal(x["profit_estimate"]), str(x["sku"])),
    )[: max(1, int(limit or 5))]

    low_stock = sorted(
        [x for x in rows if int(x.get("stock") or 0) < 10],
        key=lambda x: (int(x.get("stock") or 0), str(x["sku"])),
    )[: max(1, int(limit or 5))]

    def _serialize(x: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "product_id": x["product_id"],
            "sku": x["sku"],
            "name": x["name"],
            "stock": int(x["stock"] or 0),
            "units_sold": int(x["units_sold"] or 0),
            "orders_count": int(x["orders_count"] or 0),
            "revenue": str(_to_decimal(x["revenue"])),
            "ads_spend": str(_to_decimal(x["ads_spend"])),
            "profit_estimate": str(_to_decimal(x["profit_estimate"])),
            "roas_estimate": str(_to_decimal(x["roas_estimate"])),
        }

    headline = {
        "sku_total": len(rows),
        "sku_top_selling_count": len(top_selling),
        "sku_low_roas_count": len(low_roas),
        "sku_losing_count": len(losing_sku),
        "sku_low_stock_count": len(low_stock),
    }

    return SKURadarResult(
        headline=headline,
        blocks={
            "top_selling": [_serialize(x) for x in top_selling],
            "low_roas": [_serialize(x) for x in low_roas],
            "losing_sku": [_serialize(x) for x in losing_sku],
            "low_stock": [_serialize(x) for x in low_stock],
        },
    )