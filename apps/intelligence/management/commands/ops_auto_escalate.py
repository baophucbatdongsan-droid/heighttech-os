from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.intelligence.models import ShopActionItem


class Command(BaseCommand):
    help = "Auto escalate overdue founder actions"

    def handle(self, *args, **kwargs):
        now = timezone.now()

        qs = ShopActionItem.objects.filter(
            due_at__lt=now
        ).exclude(status__in=["done", "verified"])

        escalated = 0

        for obj in qs:
            hours_overdue = (now - obj.due_at).total_seconds() / 3600

            if hours_overdue > 48:
                obj.severity = "P0"
            elif hours_overdue > 24:
                obj.severity = "P1"

            obj.save(update_fields=["severity"])
            escalated += 1

        self.stdout.write(self.style.SUCCESS(f"Escalated: {escalated}"))