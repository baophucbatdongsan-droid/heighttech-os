# apps/events/management/commands/pump_events.py
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.events.tasks import _pump


class Command(BaseCommand):
    help = "Pump EventOutbox pending events"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=200)

    def handle(self, *args, **options):
        limit = int(options.get("limit") or 200)
        n = _pump(limit=limit)
        self.stdout.write(self.style.SUCCESS(f"Processed {n} events"))