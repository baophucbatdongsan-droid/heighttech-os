from __future__ import annotations

import secrets

from django.core.management.base import BaseCommand

from apps.accounts.models import InviteCode


class Command(BaseCommand):
    help = "Create a new invite code"

    def add_arguments(self, parser):
        parser.add_argument("--max-uses", type=int, default=10)
        parser.add_argument("--note", type=str, default="")

    def handle(self, *args, **options):
        code = secrets.token_hex(4)  # 8 chars hex
        obj = InviteCode.objects.create(
            code=code,
            max_uses=options["max_uses"],
            note=options["note"],
        )
        self.stdout.write(self.style.SUCCESS(f"Invite code: {obj.code}"))