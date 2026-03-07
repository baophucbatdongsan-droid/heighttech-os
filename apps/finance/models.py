# apps/finance/models.py
from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils import timezone


# ============================================================
# 1) AGENCY MONTHLY FINANCE (LOCK / FINALIZE CONTROL LAYER)
# ============================================================

class AgencyMonthlyFinance(models.Model):
    """
    Snapshot tài chính cấp hệ thống (Agency).
    Dùng để:
    - Tính tổng theo tháng (snapshot)
    - Khoá tháng
    - Chốt sổ
    - Audit (kèm rule snapshot)
    """

    STATUS_OPEN = "open"
    STATUS_LOCKED = "locked"
    STATUS_FINALIZED = "finalized"

    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_LOCKED, "Locked"),
        (STATUS_FINALIZED, "Finalized"),
    ]

    # NOTE:
    # Hiện tại chưa có tenant => month unique toàn cục.
    # Sau này multi-tenant thì đổi: unique_together (tenant, month)
    month = models.DateField(unique=True, db_index=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
        db_index=True,
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

    # =========================
    # RULE SNAPSHOT (Enterprise Control)
    # =========================
    rule_industry_code = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Rule Industry Code Snapshot",
    )
    rule_version = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Rule Version Snapshot",
    )
    rule_engine_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Rule Engine Name Snapshot",
    )
    rule_effective_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Rule Effective Date Snapshot",
    )
    rule_snapshot_json = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Rule Metadata Snapshot",
    )

    # =========================
    # TIMESTAMPS
    # =========================
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-month"]
        indexes = [
            models.Index(fields=["month"], name="idx_ag_fin_month"),
            models.Index(fields=["status"], name="idx_ag_fin_status"),
            models.Index(fields=["month", "status"], name="idx_ag_fin_month_status"),
        ]

    def __str__(self) -> str:
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
        # finalized thì freeze luôn
        self.status = self.STATUS_FINALIZED
        self.finalized_at = timezone.now()
        self.save(update_fields=["status", "finalized_at", "updated_at"])

    def reopen(self):
        # mở lại tháng để edit (nếu muốn)
        self.status = self.STATUS_OPEN
        self.locked_at = None
        self.finalized_at = None
        self.save(update_fields=["status", "locked_at", "finalized_at", "updated_at"])


# ============================================================
# 2) COMPANY MONTHLY SNAPSHOT (FOUNDER / DASHBOARD READ)
# ============================================================

class CompanyMonthlySnapshot(models.Model):
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="monthly_snapshots",
    )

    month = models.DateField()

    total_revenue = models.DecimalField(max_digits=18, decimal_places=0, default=0)
    total_profit = models.DecimalField(max_digits=18, decimal_places=0, default=0)
    total_net = models.DecimalField(max_digits=18, decimal_places=0, default=0)
    margin = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("company", "month")
        indexes = [
            models.Index(fields=["company", "month"], name="idx_co_snap_company_month"),
            models.Index(fields=["month"], name="idx_co_snap_month"),
        ]
        ordering = ["-month"]

    def __str__(self) -> str:
        return f"{self.company.name} - {self.month}"


# ============================================================
# 3) SHOP MONTHLY SNAPSHOT (FOUNDER HEALTH / RISK ENGINE)
# ============================================================

class ShopMonthlySnapshot(models.Model):
    shop = models.ForeignKey(
        "shops.Shop",
        on_delete=models.CASCADE,
        related_name="monthly_snapshots",
    )

    month = models.DateField()

    revenue = models.DecimalField(max_digits=18, decimal_places=0, default=0)
    profit = models.DecimalField(max_digits=18, decimal_places=0, default=0)
    net = models.DecimalField(max_digits=18, decimal_places=0, default=0)
    margin = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    score = models.IntegerField(default=100)
    risk = models.CharField(max_length=10, default="LOW")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("shop", "month")
        indexes = [
            models.Index(fields=["shop", "month"], name="idx_shop_snap_shop_month"),
            models.Index(fields=["month"], name="idx_shop_snap_month"),
        ]
        ordering = ["-month"]

    def __str__(self) -> str:
        return f"{self.shop.name} - {self.month}"