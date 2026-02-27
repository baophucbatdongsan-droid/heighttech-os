# apps/intelligence/models.py
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class ShopHealthSnapshot(models.Model):
    """
    Snapshot sức khoẻ shop theo tháng (month = YYYY-MM-01).
    Derived data => có thể recalc bất cứ lúc nào.
    """

    month = models.DateField(verbose_name="Tháng (YYYY-MM-01)")

    shop = models.ForeignKey(
        "shops.Shop",
        on_delete=models.CASCADE,
        related_name="health_snapshots",
        verbose_name="Shop",
    )
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="shop_health_snapshots",
        verbose_name="Company",
    )
    brand = models.ForeignKey(
        "brands.Brand",
        on_delete=models.CASCADE,
        related_name="shop_health_snapshots",
        verbose_name="Brand",
    )

    # 3M rolling (<= month)
    revenue_3m = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    profit_3m = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    net_3m = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    margin_3m = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    growth_last_mom = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))

    score = models.IntegerField(default=0)
    risk = models.CharField(max_length=10, default="LOW")  # HIGH/MED/LOW
    note = models.TextField(blank=True, default="")

    calculated_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Shop Health Snapshot"
        verbose_name_plural = "Shop Health Snapshots"
        unique_together = ("month", "shop")
        ordering = ("-month", "-score")
        indexes = [
            models.Index(fields=["month", "risk"], name="idx_shsnap_month_risk"),
            models.Index(fields=["month", "company"], name="idx_shsnap_month_company"),
            models.Index(fields=["month", "shop"], name="idx_shsnap_month_shop"),
        ]

    def __str__(self) -> str:
        return f"{self.month} | {self.shop.name} | {self.risk} | {self.score}"

    def touch_calculated(self):
        self.calculated_at = timezone.now()
        self.save(update_fields=["calculated_at", "updated_at"])


class FounderInsightSnapshot(models.Model):
    """
    Snapshot context founder theo tháng (và/hoặc all-time) để:
    - lưu lịch sử insight (alerts/actions/forecast/insights)
    - render nhanh Founder War Room
    """

    month = models.DateField(null=True, blank=True)  # null = all-time
    generated_at = models.DateTimeField(default=timezone.now)

    # JSON blobs
    kpi = models.JSONField(default=dict, blank=True)          # total_revenue/profit/net/margin
    forecast = models.JSONField(default=dict, blank=True)     # forecast block
    alerts = models.JSONField(default=list, blank=True)       # alert list
    actions = models.JSONField(default=list, blank=True)      # action list
    insights = models.JSONField(default=dict, blank=True)     # insight packs / ceo_summary
    shop_health = models.JSONField(default=list, blank=True)  # list(dict)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="founder_snapshots",
    )

    class Meta:
        ordering = ["-generated_at"]
        indexes = [
            models.Index(fields=["month"], name="idx_insnap_month"),
            models.Index(fields=["generated_at"], name="idx_insnap_gen"),
        ]

    def __str__(self):
        return f"Snapshot {self.month or 'all'} @ {self.generated_at:%Y-%m-%d %H:%M}"


class ShopActionItem(models.Model):
    """
    Ticket hành động để "giữ khách bằng công nghệ":
    - tự sinh từ insight (P0/P1/P2) hoặc tạo tay
    - theo dõi trạng thái, người xử lý, deadline
    """

    # ---- status ----
    STATUS_OPEN = "open"
    STATUS_DOING = "doing"
    STATUS_BLOCKED = "blocked"
    STATUS_DONE = "done"
    STATUS_VERIFIED = "verified"

    STATUS_CHOICES = [
        (STATUS_OPEN, "Mở"),
        (STATUS_DOING, "Đang làm"),
        (STATUS_BLOCKED, "Bị chặn"),
        (STATUS_DONE, "Hoàn thành"),
        (STATUS_VERIFIED, "Đã xác nhận"),
    ]

    # ---- severity ----
    SEV_P0 = "P0"
    SEV_P1 = "P1"
    SEV_P2 = "P2"
    SEVERITY_CHOICES = [
        (SEV_P0, "P0"),
        (SEV_P1, "P1"),
        (SEV_P2, "P2"),
    ]

    # ---- source ----
    SOURCE_FOUNDER_INSIGHT = "founder_insight"
    SOURCE_MANUAL = "manual"
    SOURCE_API = "api"
    SOURCE_CHOICES = [
        (SOURCE_FOUNDER_INSIGHT, "Founder Insight"),
        (SOURCE_MANUAL, "Manual"),
        (SOURCE_API, "API"),
    ]

    month = models.DateField(null=True, blank=True)  # action cho tháng nào (hoặc all-time)

    # giữ int để nhẹ, tránh phụ thuộc FK shop (đa tenant/đa nguồn)
    shop_id = models.IntegerField(db_index=True)
    company_name = models.CharField(max_length=255, blank=True, default="")
    shop_name = models.CharField(max_length=255, blank=True, default="")

    title = models.CharField(max_length=255)

    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default=SEV_P1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    source = models.CharField(max_length=50, choices=SOURCE_CHOICES, default=SOURCE_FOUNDER_INSIGHT, db_index=True)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_shop_action_items",
        verbose_name="Người xử lý",
    )

    due_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    payload = models.JSONField(default=dict, blank=True)  # store context (scores/why/flags)
    note = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["month", "shop_id"], name="idx_action_month_shop"),
            models.Index(fields=["status"], name="idx_action_status"),
            models.Index(fields=["severity"], name="idx_action_sev"),
            models.Index(fields=["source"], name="idx_action_source"),
            models.Index(fields=["due_at"], name="idx_action_due"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["month", "shop_id", "title", "source"],
                name="uq_action_month_shop_title_source",
            ),
        ]

    def __str__(self):
        return f"{self.shop_name} - {self.title} ({self.status})"

    def mark_done(self):
        self.status = self.STATUS_DONE
        self.closed_at = timezone.now()
        self.save(update_fields=["status", "closed_at", "updated_at"])

    def mark_verified(self):
        self.status = self.STATUS_VERIFIED
        if not self.closed_at:
            self.closed_at = timezone.now()
        self.save(update_fields=["status", "closed_at", "updated_at"])