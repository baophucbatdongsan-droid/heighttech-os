from __future__ import annotations

from django.db import models


class TenantUsageDaily(models.Model):
    """
    Daily usage snapshot sau khi flush từ Redis -> DB.
    Dùng tenant_id (int) để tránh phụ thuộc FK khi tenant migrations/phân tầng.
    """
    tenant_id = models.IntegerField(db_index=True)
    date = models.DateField(db_index=True)

    requests = models.BigIntegerField(default=0)
    errors = models.BigIntegerField(default=0)
    slow = models.BigIntegerField(default=0)
    rate_limited = models.BigIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("tenant_id", "date")
        indexes = [
            models.Index(fields=["tenant_id", "date"]),
        ]

    def __str__(self) -> str:
        return f"TenantUsageDaily(tenant={self.tenant_id}, date={self.date})"


class TenantUsageMonthly(models.Model):
    """
    Monthly aggregate (từ daily).
    month = ngày 1 của tháng (date) để dễ query.
    """
    tenant_id = models.IntegerField(db_index=True)
    month = models.DateField(db_index=True)  # ngày 1 của tháng

    period_start = models.DateField()
    period_end = models.DateField()

    requests = models.BigIntegerField(default=0)
    errors = models.BigIntegerField(default=0)
    slow = models.BigIntegerField(default=0)
    rate_limited = models.BigIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("tenant_id", "month")
        indexes = [
            models.Index(fields=["tenant_id", "month"]),
        ]

    def __str__(self) -> str:
        return f"TenantUsageMonthly(tenant={self.tenant_id}, month={self.month})"


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        FINAL = "final", "Final"
        PAID = "paid", "Paid"
        VOID = "void", "Void"

    tenant_id = models.IntegerField(db_index=True)
    month = models.DateField(db_index=True)  # ngày 1 của tháng
    period_start = models.DateField()
    period_end = models.DateField()

    currency = models.CharField(max_length=8, default="VND")
    total_amount = models.BigIntegerField(default=0)  # VND integer
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)

    # snapshot usage + pricing breakdown để invoice-ready
    usage_snapshot = models.JSONField(default=dict, blank=True)
    line_items = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("tenant_id", "month")
        indexes = [
            models.Index(fields=["tenant_id", "month"]),
        ]

    def __str__(self) -> str:
        return f"Invoice(tenant={self.tenant_id}, month={self.month}, status={self.status})"

# ==========================================================
# LEVEL 19: DB-DRIVEN PRICING
# ==========================================================

class PricingPlan(models.Model):
    """
    PricingPlan gắn với tenant.plan (basic/pro/enterprise).
    Có thể tạo nhiều version, sau này active theo thời gian.
    """
    code = models.CharField(max_length=32, unique=True, db_index=True)  # basic/pro/enterprise
    name = models.CharField(max_length=128, default="")
    currency = models.CharField(max_length=8, default="VND")
    is_active = models.BooleanField(default=True)

    # (optional) Free quota
    free_requests = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["code", "is_active"])]

    def __str__(self) -> str:
        return f"{self.code} ({'active' if self.is_active else 'off'})"


class PricingTier(models.Model):
    """
    Tier pricing theo block.
    from_requests: inclusive
    to_requests: exclusive (null = infinity)
    unit_price: giá/1 request trong tier (VND)
    """
    plan = models.ForeignKey("billing.PricingPlan", on_delete=models.CASCADE, related_name="tiers")

    from_requests = models.PositiveIntegerField(default=0)
    to_requests = models.PositiveIntegerField(null=True, blank=True)

    unit_price = models.PositiveIntegerField(default=0)  # VND per request
    priority = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["priority", "from_requests"]
        indexes = [
            models.Index(fields=["plan", "priority"]),
            models.Index(fields=["plan", "from_requests"]),
        ]

    def __str__(self) -> str:
        to_txt = self.to_requests if self.to_requests is not None else "inf"
        return f"{self.plan.code}: {self.from_requests} -> {to_txt} @ {self.unit_price}/req"