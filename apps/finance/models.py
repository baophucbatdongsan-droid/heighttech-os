# apps/finance/models.py

from decimal import Decimal
from django.db import models
from django.utils import timezone


# ============================================================
# 1️⃣ AGENCY MONTHLY FINANCE (LOCK / FINALIZE CONTROL LAYER)
# ============================================================

class AgencyMonthlyFinance(models.Model):
    """
    Snapshot tài chính cấp hệ thống (Agency).
    Dùng để:
    - Khoá tháng
    - Chốt sổ
    - Audit
    """

    STATUS_OPEN = "open"
    STATUS_LOCKED = "locked"
    STATUS_FINALIZED = "finalized"

    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_LOCKED, "Locked"),
        (STATUS_FINALIZED, "Finalized"),
    ]

    month = models.DateField(unique=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
    )

    # =========================
    # SNAPSHOT NUMBERS
    # =========================

    total_gmv_fee_after_tax = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0")
    )

    total_fixed_fee_net = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0")
    )

    total_sale_commission = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0")
    )

    total_team_bonus = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0")
    )

    total_operating_cost = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0")
    )

    agency_net_profit = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0")
    )

    calculated_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-month"]

    def __str__(self):
        return f"Finance {self.month} ({self.status})"

    # -------------------------
    # STATE HELPERS
    # -------------------------

    def can_edit(self) -> bool:
        return self.status == self.STATUS_OPEN

    def lock(self):
        if self.status == self.STATUS_FINALIZED:
            return
        self.status = self.STATUS_LOCKED
        self.locked_at = timezone.now()
        self.save(update_fields=["status", "locked_at", "updated_at"])

    def finalize(self):
        self.status = self.STATUS_FINALIZED
        self.finalized_at = timezone.now()
        self.save(update_fields=["status", "finalized_at", "updated_at"])


# ============================================================
# 2️⃣ COMPANY MONTHLY SNAPSHOT (FOUNDER / DASHBOARD READ)
# ============================================================

class CompanyMonthlySnapshot(models.Model):
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="monthly_snapshots",
    )

    month = models.DateField()

    total_revenue = models.DecimalField(
        max_digits=18, decimal_places=0, default=0
    )

    total_profit = models.DecimalField(
        max_digits=18, decimal_places=0, default=0
    )

    total_net = models.DecimalField(
        max_digits=18, decimal_places=0, default=0
    )

    margin = models.DecimalField(
        max_digits=8, decimal_places=2, default=0
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("company", "month")
        indexes = [
            models.Index(fields=["company", "month"]),
            models.Index(fields=["month"]),
        ]
        ordering = ["-month"]

    def __str__(self):
        return f"{self.company.name} - {self.month}"


# ============================================================
# 3️⃣ SHOP MONTHLY SNAPSHOT (FOUNDER HEALTH / RISK ENGINE)
# ============================================================

class ShopMonthlySnapshot(models.Model):
    shop = models.ForeignKey(
        "shops.Shop",
        on_delete=models.CASCADE,
        related_name="monthly_snapshots",
    )

    month = models.DateField()

    revenue = models.DecimalField(
        max_digits=18, decimal_places=0, default=0
    )

    profit = models.DecimalField(
        max_digits=18, decimal_places=0, default=0
    )

    net = models.DecimalField(
        max_digits=18, decimal_places=0, default=0
    )

    margin = models.DecimalField(
        max_digits=8, decimal_places=2, default=0
    )

    score = models.IntegerField(default=100)
    risk = models.CharField(max_length=10, default="LOW")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("shop", "month")
        indexes = [
            models.Index(fields=["shop", "month"]),
            models.Index(fields=["month"]),
        ]
        ordering = ["-month"]

    def __str__(self):
        return f"{self.shop.name} - {self.month}"