# apps/intelligence/management/commands/recalc_shop_health_latest.py
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.intelligence.services import SnapshotService
from apps.performance.models import MonthlyPerformance


class Command(BaseCommand):
    help = "Recalculate ShopHealthSnapshot for the latest month that has MonthlyPerformance data."

    def handle(self, *args, **options):
        last = (
            MonthlyPerformance.objects.order_by("-month")
            .values_list("month", flat=True)
            .first()
        )
        if not last:
            self.stdout.write(self.style.WARNING("⚠️ No MonthlyPerformance data found. Skip."))
            return

        n = SnapshotService.recalc_month(last)
        self.stdout.write(self.style.SUCCESS(f"✅ Recalculated {n} shop(s) for {last}"))