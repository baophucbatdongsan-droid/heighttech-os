# apps/intelligence/management/commands/recalc_shop_health_open_months.py
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.finance.models import AgencyMonthlyFinance
from apps.finance.services import AgencyFinanceService
from apps.intelligence.services import SnapshotService
from apps.performance.models import MonthlyPerformance


class Command(BaseCommand):
    help = (
        "C2++: Recalc ShopHealthSnapshot for months that are OPEN in AgencyMonthlyFinance.\n"
        "- Skip LOCKED/FINALIZED\n"
        "- If snapshot missing for a month that has performance data => auto create snapshot (OPEN) then recalc\n"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=12,
            help="Max number of OPEN months to process (default 12). Use 0 for no limit.",
        )
        parser.add_argument(
            "--latest-if-none",
            action="store_true",
            help="If no OPEN snapshot found, recalc latest month that has MonthlyPerformance data.",
        )

    def handle(self, *args, **options):
        limit = int(options["limit"] or 0)
        latest_if_none = bool(options["latest_if_none"])

        # OPEN months (newest first)
        open_qs = AgencyMonthlyFinance.objects.filter(
            status=AgencyMonthlyFinance.STATUS_OPEN
        ).order_by("-month")

        if limit > 0:
            open_qs = open_qs[:limit]

        months = list(open_qs.values_list("month", flat=True))

        if not months and latest_if_none:
            last = (
                MonthlyPerformance.objects.order_by("-month")
                .values_list("month", flat=True)
                .first()
            )
            if last:
                months = [last]

        if not months:
            self.stdout.write(self.style.WARNING("⚠️ No OPEN months to recalc."))
            return

        total_shops = 0
        processed = 0

        for m in months:
            with transaction.atomic():
                # Ensure snapshot exists (OPEN) so lifecycle quản trị nhất quán
                if not AgencyMonthlyFinance.objects.filter(month=m).exists():
                    AgencyFinanceService.calculate_or_update(m)

                snap = AgencyMonthlyFinance.objects.filter(month=m).first()
                if snap and not snap.can_edit():
                    self.stdout.write(self.style.WARNING(f"⏭️ Skip {m} (status={snap.status})"))
                    continue

                n = SnapshotService.recalc_month(m)
                total_shops += int(n or 0)
                processed += 1

                self.stdout.write(self.style.SUCCESS(f"✅ {m}: recalc {n} shop(s)"))

        self.stdout.write(self.style.SUCCESS(
            f"🏁 Done. Months processed={processed}, total shops recalculated={total_shops}"
        ))