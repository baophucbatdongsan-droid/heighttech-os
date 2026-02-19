# apps/tenants/models_subscription.py
from django.db import models
from django.utils import timezone


class SubscriptionTier(models.TextChoices):
    FREE = "free", "Free"
    PRO = "pro", "Pro"
    ENTERPRISE = "enterprise", "Enterprise"


class TenantSubscription(models.Model):
    tenant = models.OneToOneField(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="subscription",
    )

    tier = models.CharField(
        max_length=32,
        choices=SubscriptionTier.choices,
        default=SubscriptionTier.FREE,
    )

    max_shops = models.IntegerField(default=3)
    max_actions = models.IntegerField(default=200)

    started_at = models.DateTimeField(default=timezone.now)
    expired_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.tenant.name} - {self.tier}"