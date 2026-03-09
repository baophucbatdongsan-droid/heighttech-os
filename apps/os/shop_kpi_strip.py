from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional

from django.utils import timezone

from apps.contracts.models import ContractMilestone
from apps.products.models_stats import ProductDailyStat
from apps.work.models import WorkItem


@dataclass(frozen=True)
class ShopKPIStripResult:
    headline: Dict[str, Any]
    items: list[Dict[str, Any]]


def _to_decimal(v) -> Decimal:
    try:
        return Decimal(str(v or 0))
    except Exception:
        return Decimal("0")


def _fmt_money(v: Decimal) -> str:
    try:
        return f"{int(v):,}".replace(",", ".")
    except Exception:
        return str(v)


def build_shop_kpi_strip(
    *,
    tenant_id: int,
    company_id: Optional[int] = None,
    shop_id: Optional[int] = None,
) -> ShopKPIStripResult:
    today = timezone.localdate()
    now = timezone.now()

    # =========================
    # Sales layer
    # =========================
    stats = ProductDailyStat.objects_all.filter(
        tenant_id=int(tenant_id),
        stat_date=today,
    )

    if company_id:
        stats = stats.filter(company_id=int(company_id))
    if shop_id:
        stats = stats.filter(shop_id=int(shop_id))

    revenue_today = sum((_to_decimal(x.revenue) for x in stats), Decimal("0"))
    units_today = sum((int(x.units_sold or 0) for x in stats), 0)
    losing_sku = sum((1 for x in stats if _to_decimal(x.profit_estimate) < 0), 0)
    low_stock = sum((1 for x in stats if int(getattr(x.product, "stock", 0) or 0) < 10), 0)

    # =========================
    # Operations layer
    # =========================
    work_qs = WorkItem.objects_all.filter(tenant_id=int(tenant_id))
    if company_id:
        work_qs = work_qs.filter(company_id=int(company_id))
    if shop_id:
        work_qs = work_qs.filter(shop_id=int(shop_id))

    work_open = work_qs.exclude(
        status__in=[WorkItem.Status.DONE, WorkItem.Status.CANCELLED]
    )

    overdue_tasks = work_open.filter(
        due_at__isnull=False,
        due_at__lt=now,
    ).count()

    # =========================
    # Contract / service layer
    # =========================
    milestone_qs = ContractMilestone.objects_all.filter(
        tenant_id=int(tenant_id),
        status__in=[ContractMilestone.Status.TODO, ContractMilestone.Status.DOING],
        due_at__isnull=False,
    )

    if company_id:
        milestone_qs = milestone_qs.filter(contract__company_id=int(company_id))
    if shop_id:
        milestone_qs = milestone_qs.filter(contract__contract_shops__shop_id=int(shop_id)).distinct()

    milestone_due = milestone_qs.filter(
        due_at__gte=now,
        due_at__lte=now + timezone.timedelta(days=3),
    ).count()

    headline = {
        "shop_kpi_revenue_today": str(revenue_today),
        "shop_kpi_units_today": units_today,
        "shop_kpi_losing_sku": losing_sku,
        "shop_kpi_low_stock": low_stock,
        "shop_kpi_overdue_tasks": overdue_tasks,
        "shop_kpi_milestone_due": milestone_due,
    }

    items = [
        {
            "key": "revenue_today",
            "label": "Revenue Today",
            "value": _fmt_money(revenue_today),
            "unit": "đ",
        },
        {
            "key": "units_today",
            "label": "Units Sold",
            "value": str(units_today),
            "unit": "",
        },
        {
            "key": "losing_sku",
            "label": "SKU Losing",
            "value": str(losing_sku),
            "unit": "",
        },
        {
            "key": "low_stock",
            "label": "Low Stock",
            "value": str(low_stock),
            "unit": "",
        },
        {
            "key": "overdue_tasks",
            "label": "Tasks Overdue",
            "value": str(overdue_tasks),
            "unit": "",
        },
        {
            "key": "milestone_due",
            "label": "Milestones Due",
            "value": str(milestone_due),
            "unit": "",
        },
    ]

    return ShopKPIStripResult(
        headline=headline,
        items=items,
    )