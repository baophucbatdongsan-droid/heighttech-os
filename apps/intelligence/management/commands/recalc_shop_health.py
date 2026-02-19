# apps/intelligence/management/commands/recalc_shop_health.py
from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_date

from apps.intelligence.services import SnapshotService


class Command(BaseCommand):
    help = "Recalculate ShopHealthSnapshot for a month (YYYY-MM-01)."

    def add_arguments(self, parser):
        parser.add_argument("--month", required=True, help="YYYY-MM-01")

    def handle(self, *args, **options):
        month_str = options["month"]
        dt = parse_date(month_str)
        if not dt:
            self.stdout.write(self.style.ERROR("❌ Invalid month. Use YYYY-MM-01"))
            return

        n = SnapshotService.recalc_month(dt)
        self.stdout.write(self.style.SUCCESS(f"✅ Recalculated snapshots: {n} shop(s) for {dt}"))