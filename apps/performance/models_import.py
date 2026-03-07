# apps/performance/models_import.py
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.managers import TenantAllManager, TenantManager
from apps.shops.models import Shop


# ==========================================================
# IMPORT JOB
# ==========================================================
class ImportJob(models.Model):
    """
    Lưu lịch sử import CSV MonthlyPerformance (chuẩn SaaS multi-tenant).
    Tương thích đúng với apps/api/v1/imports.py bạn đang dùng.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="import_jobs",
        db_index=True,
        verbose_name="Tenant",
    )

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="import_jobs",
        verbose_name="Actor",
    )

    filename = models.CharField(max_length=255, blank=True, default="", verbose_name="Tên file")
    file_size = models.BigIntegerField(default=0, verbose_name="Dung lượng (bytes)")
    dry_run = models.BooleanField(default=True, verbose_name="Chạy thử (dry-run)")

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Chờ"),
        (STATUS_RUNNING, "Đang chạy"),
        (STATUS_SUCCESS, "Thành công"),
        (STATUS_FAILED, "Thất bại"),
    ]

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
        verbose_name="Trạng thái",
    )

    total_rows = models.IntegerField(default=0, verbose_name="Tổng dòng")
    valid_rows = models.IntegerField(default=0, verbose_name="Dòng hợp lệ")
    error_rows = models.IntegerField(default=0, verbose_name="Dòng lỗi")

    created = models.IntegerField(default=0, verbose_name="Tạo mới")
    updated = models.IntegerField(default=0, verbose_name="Cập nhật")

    months_touched = models.JSONField(null=True, blank=True, verbose_name="Các tháng bị ảnh hưởng")
    preview = models.JSONField(null=True, blank=True, verbose_name="Preview (tối đa 30)")
    errors_preview = models.JSONField(null=True, blank=True, verbose_name="Lỗi preview (tối đa 200)")

    message = models.TextField(blank=True, default="", verbose_name="Ghi chú / thông báo")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="Bắt đầu lúc")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="Kết thúc lúc")

    created_at = models.DateTimeField(default=timezone.now, verbose_name="Tạo lúc")

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        ordering = ["-id"]
        verbose_name = "Lịch sử import"
        verbose_name_plural = "Lịch sử import"
        indexes = [
            models.Index(fields=["tenant", "created_at"], name="idx_importjob_tenant_time"),
            models.Index(fields=["status"], name="idx_importjob_status"),
            models.Index(fields=["created_at"], name="idx_importjob_created_at"),
        ]

    def __str__(self) -> str:
        return f"ImportJob#{self.pk} {self.status} {self.filename}".strip()

    def save(self, *args, **kwargs):
        # auto sync tenant từ context nếu chưa set (middleware set_current_tenant)
        if not self.tenant_id:
            try:
                from apps.core.tenant_context import get_current_tenant

                t = get_current_tenant()
                if t is not None:
                    self.tenant = t
            except Exception:
                pass
        super().save(*args, **kwargs)


# ==========================================================
# MONTHLY PERFORMANCE
# ==========================================================
class MonthlyPerformance(models.Model):
    """
    Hiệu suất theo tháng - scoped theo tenant.
    SINGLE SOURCE OF TRUTH: tính toán qua apps.performance.services.PerformanceCalculator
    Rule Engine: apps.rules (founder-controlled)
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="monthly_performances",
        db_index=True,
        verbose_name="Tenant",
    )

    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name="performances",
        verbose_name="Shop",
    )

    month = models.DateField(verbose_name="Tháng (YYYY-MM-01)")

    # INPUT
    revenue = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"), verbose_name="GMV / Doanh thu")
    cost = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"), verbose_name="Chi phí")

    fixed_fee = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"), verbose_name="Phí cứng (gross)")
    vat_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"), verbose_name="VAT % (0/8/10)")
    sale_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"), verbose_name="Sale % (3-6)")

    # AUTO (CALCULATED)
    service_percent = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0"), verbose_name="% GMV fee")
    percent_fee_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"), verbose_name="GMV fee gross")
    gmv_fee_after_tax = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"), verbose_name="GMV fee after tax (70%)")

    fixed_fee_net = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"), verbose_name="Phí cứng net (trừ VAT)")
    fixed_fee_net_after_tax = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"), verbose_name="Phí cứng net after tax")

    profit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"), verbose_name="Profit (base)")
    growth_percent = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"), verbose_name="Growth %")

    bonus_percent = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0"), verbose_name="Bonus %")
    bonus_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"), verbose_name="Team bonus amount")

    sale_commission = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"), verbose_name="Sale commission")
    company_net_profit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"), verbose_name="Company net profit")

    created_at = models.DateTimeField(default=timezone.now, verbose_name="Tạo lúc")

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        verbose_name = "Hiệu suất theo tháng"
        verbose_name_plural = "Hiệu suất theo tháng"
        ordering = ["-month"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "shop", "month"], name="uq_perf_tenant_shop_month"),
        ]
        indexes = [
            models.Index(fields=["tenant"], name="idx_perf_tenant"),
            models.Index(fields=["month"], name="idx_perf_month"),
            models.Index(fields=["tenant", "month"], name="idx_perf_tenant_month"),
            models.Index(fields=["shop", "month"], name="idx_perf_shop_month"),
        ]

    def __str__(self) -> str:
        return f"{getattr(self.shop, 'name', self.shop_id)} - {self.month}"

    # -------------------------
    # FINANCE MONTH STATE GUARD
    # -------------------------
    def _ensure_month_editable(self) -> None:
        """
        Chặn sửa MonthlyPerformance nếu tháng đã LOCKED/FINALIZED.
        Áp dụng khi bạn chốt sổ AgencyMonthlyFinance.
        """
        from apps.finance.models import AgencyMonthlyFinance

        snap = AgencyMonthlyFinance.objects.filter(month=self.month).only("status").first()
        if not snap:
            return

        locked = getattr(AgencyMonthlyFinance, "STATUS_LOCKED", "locked")
        finalized = getattr(AgencyMonthlyFinance, "STATUS_FINALIZED", "finalized")

        if snap.status in {locked, finalized}:
            raise ValidationError(
                {"month": f"Month {self.month} is {snap.status.upper()}. MonthlyPerformance is read-only."}
            )

    def save(self, *args, **kwargs):
        # auto sync tenant từ shop nếu chưa set
        if not self.tenant_id and self.shop_id:
            try:
                self.tenant_id = self.shop.tenant_id
            except Exception:
                pass

        # chặn edit nếu tháng đã khóa/chốt
        self._ensure_month_editable()

        # ===== growth theo tháng trước =====
        prev_qs = MonthlyPerformance.objects.filter(shop=self.shop, month__lt=self.month)
        if self.pk:
            prev_qs = prev_qs.exclude(pk=self.pk)
        prev = prev_qs.order_by("-month").only("revenue").first()

        if prev and prev.revenue and prev.revenue > 0:
            self.growth_percent = ((self.revenue - prev.revenue) / prev.revenue) * Decimal("100")
        elif not prev and self.revenue and self.revenue > 0:
            self.growth_percent = Decimal("100")
        else:
            self.growth_percent = Decimal("0")

        # ===== months_active =====
        base_count = MonthlyPerformance.objects.filter(shop=self.shop).count()
        months_active = base_count if self.pk else (base_count + 1)

        # ===== SINGLE SOURCE: tính toàn bộ các cột NOT NULL tại đây =====
        # (service_percent, percent_fee_amount, gmv_fee_after_tax, profit, bonus_percent, bonus_amount,
        #  fixed_fee_net, fixed_fee_net_after_tax, sale_commission, company_net_profit, ...)
        from apps.performance.services import PerformanceCalculator

        PerformanceCalculator(self, months_active=months_active).calculate()

        super().save(*args, **kwargs)