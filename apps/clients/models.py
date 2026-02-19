from django.db import models


class Client(models.Model):

    # =============================
    # Liên kết công ty
    # =============================
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="clients",
        verbose_name="Công ty"
    )

    # =============================
    # Thông tin thương hiệu
    # =============================
    brand_name = models.CharField(
        max_length=255,
        verbose_name="Tên thương hiệu"
    )

    contract_start = models.DateField(
        verbose_name="Ngày bắt đầu hợp đồng"
    )

    contract_end = models.DateField(
        verbose_name="Ngày kết thúc hợp đồng"
    )

    # =============================
    # Phí dịch vụ
    # =============================
    fixed_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Phí cố định"
    )

    percent_fee = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="Phần trăm phí (%)"
    )

    # =============================
    # Nhân sự phụ trách
    # =============================

    account_manager = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_clients",
        verbose_name="Account phụ trách"
    )

    operator = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operated_clients",
        verbose_name="Nhân viên vận hành"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Ngày tạo"
    )

    class Meta:
        verbose_name = "Khách hàng"
        verbose_name_plural = "Khách hàng"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.brand_name} - {self.company.name}"