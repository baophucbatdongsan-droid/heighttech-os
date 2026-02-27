# apps/shops/signals.py
from __future__ import annotations

from datetime import date

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from apps.shops.models import Shop
from apps.core.audit import disable_audit_signals
from apps.core.tenant_context import set_current_tenant, clear_current_tenant


def _month_first_day(d: date) -> date:
    return d.replace(day=1)


def _add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return date(y, m, 1)


@receiver(post_save, sender=Shop)
def auto_seed_monthly_performance(sender, instance: Shop, created: bool, **kwargs):
    if not created:
        return

    from apps.performance.models import MonthlyPerformance  # local import

    base = _month_first_day(timezone.localdate())
    months = [_add_months(base, -i) for i in range(0, 12)]

    field_names = {f.name for f in MonthlyPerformance._meta.get_fields()}

    # seed không cần audit log -> tránh spam
    with disable_audit_signals():
        set_current_tenant(instance.tenant)
        try:
            for m in months:
                defaults = {"revenue": 0}

                if "fixed_fee" in field_names:
                    defaults["fixed_fee"] = 0
                if "vat_percent" in field_names:
                    defaults["vat_percent"] = 10
                if "sale_percent" in field_names:
                    defaults["sale_percent"] = 0

                MonthlyPerformance.objects.get_or_create(
                    tenant=instance.tenant,
                    shop=instance,
                    month=m,
                    defaults=defaults,
                )
        finally:
            clear_current_tenant()