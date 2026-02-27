from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


# ===============================
# ROLE CHO MEMBERSHIP (INTERNAL)
# ===============================
ROLE_FOUNDER = "founder"
ROLE_HEAD = "head"
ROLE_ACCOUNT = "account"
ROLE_SALE = "sale"
ROLE_OPERATOR = "operator"

ROLE_CHOICES = (
    (ROLE_FOUNDER, "Founder"),
    (ROLE_HEAD, "Head"),
    (ROLE_ACCOUNT, "Account"),
    (ROLE_SALE, "Sale"),
    (ROLE_OPERATOR, "Operator"),
)


# ===============================
# USER (KHÔNG GẮN COMPANY TRỰC TIẾP)
# ===============================
class User(AbstractUser):
    """
    User hệ thống.
    - Không gắn company trực tiếp.
    - Company scope qua accounts.Membership (nội bộ).
    - Client scope qua shops.ShopMember (chủ shop).
    """
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Nhân sự"
        verbose_name_plural = "Nhân sự"

    def __str__(self) -> str:
        return self.username


# ===============================
# MEMBERSHIP: USER - COMPANY - ROLE
# ===============================
class Membership(models.Model):
    """
    1 user có thể thuộc nhiều company (multi-company).
    Mỗi company có role khác nhau.
    ✅ 2 chiều:
      - Nội bộ: dựa vào Membership
      - Chủ shop/client: dựa vào shops.ShopMember (không nằm ở đây)
    """

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="memberships",
    )

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="members",
    )

    role = models.CharField(
        max_length=50,
        choices=ROLE_CHOICES,
        db_index=True,
    )

    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Phân quyền công ty"
        verbose_name_plural = "Phân quyền công ty"
        constraints = [
            models.UniqueConstraint(fields=["user", "company"], name="uq_membership_user_company"),
        ]
        indexes = [
            models.Index(fields=["user", "is_active"], name="idx_mship_user_active"),
            models.Index(fields=["company", "is_active"], name="idx_mship_company_active"),
            models.Index(fields=["role"], name="idx_mship_role"),
        ]

    def __str__(self) -> str:
        return f"{self.user.username} - {self.company.name} ({self.role})"