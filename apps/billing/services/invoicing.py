from __future__ import annotations

import calendar
from datetime import date
from typing import Tuple

from django.db import transaction
from django.db.models import Sum

from apps.billing.models import TenantUsageDaily, TenantUsageMonthly, Invoice
from apps.billing.pricing import calc_invoice_amount
from apps.tenants.models import Tenant


def month_range(year: int, month: int) -> Tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


@transaction.atomic
def aggregate_month(tenant_id: int, year: int, month: int) -> TenantUsageMonthly:
    start, end = month_range(year, month)

    agg = TenantUsageDaily.objects.filter(
        tenant_id=tenant_id,
        date__gte=start,
        date__lte=end,
    ).aggregate(
        requests=Sum("requests"),
        errors=Sum("errors"),
        slow=Sum("slow"),
        rate_limited=Sum("rate_limited"),
    )

    defaults = {
        "period_start": start,
        "period_end": end,
        "requests": int(agg["requests"] or 0),
        "errors": int(agg["errors"] or 0),
        "slow": int(agg["slow"] or 0),
        "rate_limited": int(agg["rate_limited"] or 0),
    }

    obj, _ = TenantUsageMonthly.objects.update_or_create(
        tenant_id=tenant_id,
        year=year,
        month=month,
        defaults=defaults,
    )
    return obj


@transaction.atomic
def build_invoice_preview(tenant: Tenant, year: int, month: int) -> Invoice:
    usage = aggregate_month(tenant.id, year, month)

    total, items = calc_invoice_amount(getattr(tenant, "plan", "basic"), usage.requests)

    inv_defaults = {
        "period_start": usage.period_start,
        "period_end": usage.period_end,
        "currency": "VND",
        "total_amount": total,
        "status": Invoice.Status.DRAFT,
        "usage_snapshot": {
            "requests": usage.requests,
            "errors": usage.errors,
            "slow": usage.slow,
            "rate_limited": usage.rate_limited,
        },
        "line_items": items,
    }

    inv, _ = Invoice.objects.update_or_create(
        tenant=tenant,
        year=year,
        month=month,
        defaults=inv_defaults,
    )
    return inv