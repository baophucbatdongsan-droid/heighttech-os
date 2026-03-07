# apps/events/management/commands/events_worker.py
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.events.worker import dispatch_forever


class Command(BaseCommand):
    help = "Run Outbox events worker"

    def add_arguments(self, parser):
        parser.add_argument("--sleep", type=float, default=0.5)
        parser.add_argument("--max-attempts", type=int, default=12)
        parser.add_argument("--lease-ttl", type=int, default=300)

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("events_worker started"))
        dispatch_forever(
            sleep_seconds=options["sleep"],
            max_attempts=options["max_attempts"],
            lease_ttl_seconds=options["lease_ttl"],
        )