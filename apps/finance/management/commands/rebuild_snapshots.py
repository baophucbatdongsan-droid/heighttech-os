from django.core.management.base import BaseCommand
from apps.finance.services import SnapshotService


class Command(BaseCommand):
    help = "Rebuild monthly snapshot"

    def add_arguments(self, parser):
        parser.add_argument("--month", required=True)

    def handle(self, *args, **options):
        month = options["month"]
        SnapshotService.rebuild_month(month)
        self.stdout.write(self.style.SUCCESS("Snapshot rebuilt"))