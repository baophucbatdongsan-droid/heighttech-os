from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.managers import TenantManager, TenantAllManager
from apps.companies.models import Company
from apps.shops.models import Shop


class Booking(models.Model):
    """
    Booking / đơn đặt lịch / đơn dịch vụ (tuỳ bạn map sau).
    Scoped theo tenant, gắn company + shop.
    """
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="bookings",
        db_index=True,
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="bookings",
        db_index=True,
    )
    shop = models.ForeignKey(
        Shop,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bookings",
        db_index=True,
    )

    STATUS_DRAFT = "draft"
    STATUS_CONFIRMED = "confirmed"
    STATUS_DONE = "done"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_DONE, "Done"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    code = models.CharField(max_length=50, blank=True, default="", db_index=True)
    title = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)

    amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    scheduled_at = models.DateTimeField(null=True, blank=True, db_index=True)

    note = models.TextField(blank=True, default="")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_bookings",
    )

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["tenant", "company"], name="idx_booking_tenant_company"),
            models.Index(fields=["tenant", "status"], name="idx_booking_tenant_status"),
            models.Index(fields=["tenant", "scheduled_at"], name="idx_booking_tenant_sched"),
        ]

    def save(self, *args, **kwargs):
        if not self.tenant_id and self.company_id:
            self.tenant_id = self.company.tenant_id
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.code or f"Booking#{self.pk}"


class BookingItem(models.Model):
    """
    Nếu 1 booking có nhiều dòng dịch vụ.
    """
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="booking_items", db_index=True)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="items", db_index=True)

    name = models.CharField(max_length=255)
    qty = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    total_price = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))

    created_at = models.DateTimeField(default=timezone.now)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["tenant", "booking"], name="idx_bitem_tenant_booking"),
        ]

    def save(self, *args, **kwargs):
        if not self.tenant_id and self.booking_id:
            self.tenant_id = self.booking.tenant_id
        # auto calc
        self.total_price = (self.unit_price or Decimal("0")) * Decimal(str(self.qty or 0))
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name