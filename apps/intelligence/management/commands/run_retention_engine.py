from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_date
from datetime import date

from apps.intelligence.retention_engine import RetentionEngine


class Command(BaseCommand):
    help = "Run nightly retention engine"

    def add_arguments(self, parser):
        parser.add_argument("--month", type=str, default="")

    def handle(self, *args, **opts):
        month_str = (opts.get("month") or "").strip()

        if month_str:
            month = parse_date(month_str)
        else:
            today = date.today()
            month = today.replace(day=1)

        RetentionEngine.calculate(month)

        self.stdout.write(self.style.SUCCESS(f"Retention calculated for {month}"))