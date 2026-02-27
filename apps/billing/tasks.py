from __future__ import annotations

import datetime

from celery import shared_task
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.tenants.models import Tenant
from apps.billing.models import TenantUsageDaily
from apps.billing.metering import get_usage_value, reset_usage_for_day

from apps.billing.services import build_invoice_preview
from apps.billing.services.invoice_generator import generate_monthly_invoices
from apps.billing.services.enforcement import enforce_suspensions


def _lock(key: str, ttl: int = 60) -> bool:
    return bool(cache.add(key, "1", timeout=ttl))


@shared_task
def flush_usage_for_date(date_str: str | None = None) -> int:
    if date_str:
        d = datetime.date.fromisoformat(date_str)
    else:
        d = timezone.localdate()

    lock_key = f"lock:billing:flush:{d.isoformat()}"
    if not _lock(lock_key, ttl=120):
        return 0

    tenants = Tenant.objects.filter(is_active=True).values_list("id", flat=True)
    flushed = 0

    for tid in tenants:
        per_lock = f"lock:billing:flush:{d.isoformat()}:tenant:{tid}"
        if not _lock(per_lock, ttl=30):
            continue

        requests = int(get_usage_value(tid, d, "requests") or 0)
        errors = int(get_usage_value(tid, d, "errors") or 0)
        slow = int(get_usage_value(tid, d, "slow") or 0)
        rate_limited = int(get_usage_value(tid, d, "rate_limited") or 0)

        if requests == 0 and errors == 0 and slow == 0 and rate_limited == 0:
            continue

        with transaction.atomic():
            TenantUsageDaily.objects.update_or_create(
                tenant_id=tid,
                date=d,
                defaults={
                    "requests": requests,
                    "errors": errors,
                    "slow": slow,
                    "rate_limited": rate_limited,
                },
            )

        try:
            reset_usage_for_day(tid, d)
        except Exception:
            pass

        flushed += 1

    return flushed


@shared_task
def warmup_founder_summary(days: int = 7) -> dict:
    from apps.billing.founder import compute_founder_summary
    summary = compute_founder_summary(days=days)
    cache.set(f"founder:summary:{days}d", summary, timeout=300)
    return summary


@shared_task
def generate_invoice_preview_for_month(year: int, month: int) -> int:
    lock_key = f"lock:billing:invoice-preview:{year}-{month:02d}"
    if not _lock(lock_key, ttl=300):
        return 0

    tenants = Tenant.objects.filter(is_active=True)
    n = 0
    for t in tenants:
        build_invoice_preview(t, year, month)
        n += 1
    return n


@shared_task
def generate_monthly_invoices_task() -> dict:
    # default: tháng trước
    return generate_monthly_invoices()


@shared_task
def enforce_suspensions_task(grace_days: int = 7) -> int:
    return enforce_suspensions(grace_days=grace_days)