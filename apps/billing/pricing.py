# apps/billing/pricing.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class PlanPricing:
    base_fee: int                 # phí cố định / tháng
    included_requests: int        # request free
    overage_per_1k_requests: int  # giá vượt cho mỗi 1000 requests
    currency: str = "VND"


# ==========================================================
# PRICING TABLE (VND)
# ==========================================================
PRICING_TABLE: Dict[str, PlanPricing] = {
    "basic": PlanPricing(base_fee=0, included_requests=50_000, overage_per_1k_requests=2_000),
    "pro": PlanPricing(base_fee=499_000, included_requests=300_000, overage_per_1k_requests=1_500),
    "enterprise": PlanPricing(base_fee=2_999_000, included_requests=2_000_000, overage_per_1k_requests=1_000),
}


def get_pricing(plan: str) -> PlanPricing:
    return PRICING_TABLE.get((plan or "").lower(), PRICING_TABLE["basic"])


def format_money(amount: int, currency: str = "VND") -> str:
    # Optional helper (không bắt buộc dùng)
    try:
        return f"{amount:,} {currency}".replace(",", ".")
    except Exception:
        return f"{amount} {currency}"


def calc_invoice_amount(plan: str, monthly_requests: int) -> Tuple[int, List[dict]]:
    """
    Tính tiền theo plan + tổng requests trong tháng.
    Return:
      total_amount (int), line_items (list[dict])
    """
    p = get_pricing(plan)

    base = int(p.base_fee)
    over = max(0, int(monthly_requests) - int(p.included_requests))

    # làm tròn lên từng block 1000
    over_units = (over + 999) // 1000
    over_fee = int(over_units) * int(p.overage_per_1k_requests)

    items: List[dict] = [
        {
            "code": "base_fee",
            "name": "Base fee",
            "qty": 1,
            "unit_price": base,
            "amount": base,
        },
        {
            "code": "requests_overage",
            "name": f"Requests overage (per 1k), included={p.included_requests}",
            "qty": int(over_units),
            "unit_price": int(p.overage_per_1k_requests),
            "amount": int(over_fee),
        },
    ]

    total = int(base + over_fee)
    return total, items