from django.db import models
from django.utils import timezone


class InviteCode(models.Model):

    code = models.CharField(max_length=32, unique=True)

    created_at = models.DateTimeField(default=timezone.now)

    max_uses = models.IntegerField(default=5)

    used_count = models.IntegerField(default=0)

    is_active = models.BooleanField(default=True)

    note = models.CharField(max_length=255, blank=True)

    def can_use(self):
        return self.is_active and self.used_count < self.max_uses

    def mark_used(self):
        self.used_count += 1
        self.save(update_fields=["used_count"])