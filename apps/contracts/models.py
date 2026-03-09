from __future__ import annotations

from django.db import models
from django.utils import timezone

from apps.core.managers import TenantAllManager, TenantManager


class Contract(models.Model):
    class Type(models.TextChoices):
        BOOKING = "booking", "Booking KOC/KOL"
        CHANNEL = "channel", "Xây kênh"
        OPERATION = "operation", "Vận hành"

    class Status(models.TextChoices):
        DRAFT = "draft", "Nháp"
        ACTIVE = "active", "Đang hiệu lực"
        PAUSED = "paused", "Tạm dừng"
        DONE = "done", "Hoàn thành"
        CANCELLED = "cancelled", "Huỷ"

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, db_index=True)
    company = models.ForeignKey(
        "companies.Company",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_index=True,
        related_name="contracts",
    )

    code = models.CharField(max_length=120, db_index=True)
    name = models.CharField(max_length=255, db_index=True)

    contract_type = models.CharField(
        max_length=30,
        choices=Type.choices,
        default=Type.OPERATION,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )

    partner_name = models.CharField(max_length=255, blank=True, default="")
    signed_at = models.DateField(null=True, blank=True, db_index=True)
    start_date = models.DateField(null=True, blank=True, db_index=True)
    end_date = models.DateField(null=True, blank=True, db_index=True)

    total_value = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    vat_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    note = models.TextField(blank=True, default="")
    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["tenant", "contract_type", "status"], name="ct_t_tp_st_idx"),
            models.Index(fields=["tenant", "company", "status"], name="ct_t_co_st_idx"),
            models.Index(fields=["tenant", "start_date", "end_date"], name="ct_t_sd_ed_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="uq_contract_tenant_code"),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class ContractShop(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, db_index=True)
    contract = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.CASCADE,
        related_name="contract_shops",
        db_index=True,
    )
    shop = models.ForeignKey(
        "shops.Shop",
        on_delete=models.CASCADE,
        related_name="shop_contracts",
        db_index=True,
    )

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["tenant", "contract"], name="cshop_t_ct_idx"),
            models.Index(fields=["tenant", "shop"], name="cshop_t_sh_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["contract", "shop"], name="uq_contract_shop"),
        ]

    def __str__(self) -> str:
        return f"Contract#{self.contract_id} - Shop#{self.shop_id}"


class ContractMilestone(models.Model):
    class Kind(models.TextChoices):
        KPI = "kpi", "KPI"
        ACCEPTANCE = "acceptance", "Nghiệm thu"
        DELIVERY = "delivery", "Bàn giao"
        PAYMENT_CONDITION = "payment_condition", "Điều kiện thanh toán"
        OTHER = "other", "Khác"

    class Status(models.TextChoices):
        TODO = "todo", "Chưa xử lý"
        DOING = "doing", "Đang xử lý"
        DONE = "done", "Hoàn thành"
        CANCELLED = "cancelled", "Huỷ"

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, db_index=True)
    contract = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.CASCADE,
        related_name="milestones",
        db_index=True,
    )
    company = models.ForeignKey(
        "companies.Company",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_index=True,
    )
    shop = models.ForeignKey(
        "shops.Shop",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_index=True,
    )

    title = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True, default="")
    kind = models.CharField(max_length=30, choices=Kind.choices, default=Kind.OTHER, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TODO, db_index=True)

    due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    done_at = models.DateTimeField(null=True, blank=True, db_index=True)

    sort_order = models.PositiveIntegerField(default=1, db_index=True)
    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        ordering = ["sort_order", "id"]
        indexes = [
            models.Index(fields=["tenant", "contract", "status"], name="cms_t_ct_st_idx"),
            models.Index(fields=["tenant", "due_at", "status"], name="cms_t_due_st_idx"),
            models.Index(fields=["tenant", "shop", "status"], name="cms_t_sh_st_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.contract_id})"


class ContractPayment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Chờ thanh toán"
        PARTIAL = "partial", "Thanh toán một phần"
        PAID = "paid", "Đã thanh toán"
        OVERDUE = "overdue", "Quá hạn"
        CANCELLED = "cancelled", "Huỷ"

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, db_index=True)
    contract = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.CASCADE,
        related_name="payments",
        db_index=True,
    )
    milestone = models.ForeignKey(
        "contracts.ContractMilestone",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payments",
        db_index=True,
    )

    title = models.CharField(max_length=255, db_index=True)

    # Số tiền trước VAT
    amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0,
        help_text="Số tiền gốc trước VAT",
    )

    vat_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Phần trăm VAT áp dụng cho dòng thanh toán này",
    )

    vat_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0,
        help_text="Tiền VAT của dòng thanh toán này",
    )

    total_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0,
        help_text="Tổng tiền phải thanh toán = amount + vat_amount",
    )

    due_at = models.DateTimeField(null=True, blank=True, db_index=True)

    paid_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    paid_at = models.DateTimeField(null=True, blank=True, db_index=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    note = models.TextField(blank=True, default="")
    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        ordering = ["due_at", "id"]
        indexes = [
            models.Index(fields=["tenant", "contract", "status"], name="cp_t_ct_st_idx"),
            models.Index(fields=["tenant", "due_at", "status"], name="cp_t_due_st_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.title} - {self.total_amount}"


class ContractBookingItem(models.Model):
    class BookingType(models.TextChoices):
        FREE_CAST = "free_cast", "Free cast / đơn giá cố định"
        PERCENT_DEAL = "percent_deal", "% giá trị hợp đồng"

    class PayoutStatus(models.TextChoices):
        PENDING = "pending", "Chờ thanh toán"
        PAID = "paid", "Đã thanh toán"
        CANCELLED = "cancelled", "Huỷ"

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, db_index=True)
    contract = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.CASCADE,
        related_name="booking_items",
        db_index=True,
    )
    company = models.ForeignKey(
        "companies.Company",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_index=True,
    )
    shop = models.ForeignKey(
        "shops.Shop",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_index=True,
    )

    koc_name = models.CharField(max_length=255, db_index=True)
    koc_channel_name = models.CharField(max_length=255, blank=True, default="")
    koc_channel_link = models.URLField(blank=True, default="")

    booking_type = models.CharField(
        max_length=30,
        choices=BookingType.choices,
        default=BookingType.FREE_CAST,
        db_index=True,
    )

    unit_price = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    commission_percent = models.DecimalField(max_digits=7, decimal_places=2, default=0)

    expected_post_count = models.PositiveIntegerField(default=1)
    delivered_post_count = models.PositiveIntegerField(default=0)

    brand_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0,
        help_text="Số tiền nhãn hàng / khách thanh toán cho deal này nếu cần theo dõi riêng",
    )
    payout_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0,
        help_text="Số tiền phải thanh toán cho KOC",
    )

    air_date = models.DateTimeField(null=True, blank=True, db_index=True)
    video_link = models.URLField(blank=True, default="")

    payout_due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    payout_paid_at = models.DateTimeField(null=True, blank=True, db_index=True)
    payout_status = models.CharField(
        max_length=20,
        choices=PayoutStatus.choices,
        default=PayoutStatus.PENDING,
        db_index=True,
    )

    note = models.TextField(blank=True, default="")
    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["tenant", "contract"], name="cbi_t_ct_idx"),
            models.Index(fields=["tenant", "shop"], name="cbi_t_sh_idx"),
            models.Index(fields=["tenant", "air_date"], name="cbi_t_air_idx"),
            models.Index(fields=["tenant", "payout_due_at", "payout_status"], name="cbi_t_paydue_st_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.koc_name} - Contract#{self.contract_id}"