# apps/billing/management/commands/setup_billing_beat.py
from __future__ import annotations

import json
from django.core.management.base import BaseCommand
from django_celery_beat.models import CrontabSchedule, PeriodicTask


class Command(BaseCommand):
    help = "Setup billing periodic tasks (django-celery-beat)"

    def handle(self, *args, **options):

        # ==========================================================
        # 1) Flush usage daily (Redis -> DB) at 00:05
        # ==========================================================
        s1, _ = CrontabSchedule.objects.get_or_create(
            minute="5",
            hour="0",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
        )

        PeriodicTask.objects.update_or_create(
            name="billing_flush_daily",
            defaults={
                "crontab": s1,
                "task": "apps.billing.tasks.flush_usage_for_date",
                "args": json.dumps([]),
                "kwargs": json.dumps({}),
                "enabled": True,
            },
        )

        # ==========================================================
        # 2) Founder summary warmup (7 days) at 00:10
        # ==========================================================
        s2, _ = CrontabSchedule.objects.get_or_create(
            minute="10",
            hour="0",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
        )

        PeriodicTask.objects.update_or_create(
            name="billing_founder_summary_7d",
            defaults={
                "crontab": s2,
                "task": "apps.billing.tasks.warmup_founder_summary",
                "args": json.dumps([7]),
                "kwargs": json.dumps({}),
                "enabled": True,
            },
        )

        # ==========================================================
        # 3) Generate monthly invoices (auto month) at 01:00 daily
        # Task tự tính tháng trước → không cần args
        # ==========================================================
        s3, _ = CrontabSchedule.objects.get_or_create(
            minute="0",
            hour="1",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
        )

        PeriodicTask.objects.update_or_create(
            name="billing_generate_monthly_invoices",
            defaults={
                "crontab": s3,
                "task": "apps.billing.tasks.generate_monthly_invoices_task",
                "args": json.dumps([]),
                "kwargs": json.dumps({}),
                "enabled": True,
            },
        )

        # ==========================================================
        # 4) Enforce suspensions every 30 minutes
        # ==========================================================
        s4, _ = CrontabSchedule.objects.get_or_create(
            minute="*/30",
            hour="*",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
        )

        PeriodicTask.objects.update_or_create(
            name="billing_enforce_suspensions",
            defaults={
                "crontab": s4,
                "task": "apps.billing.tasks.enforce_suspensions_task",
                "args": json.dumps([]),
                "kwargs": json.dumps({"grace_days": 7}),
                "enabled": True,
            },
        )

        self.stdout.write(
            self.style.SUCCESS("✅ Billing beat schedules are set up (Production Mode).")
        )