from django.contrib.auth.models import AbstractUser
from django.db import models

# ===============================
# ROLE CHO MEMBERSHIP
# ===============================
ROLE_CHOICES = (
    ("founder", "Founder"),
    ("head", "Head"),
    ("account", "Account"),
    ("sale", "Sale"),
    ("operator", "Operator"),
)


# ===============================
# USER GỐC (KHÔNG GẮN COMPANY TRỰC TIẾP)
# ===============================
class User(AbstractUser):
    """
    User hệ thống.
    KHÔNG gắn company trực tiếp.
    Company sẽ quản lý qua Membership.
    """

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Nhân sự"
        verbose_name_plural = "Nhân sự"

    def __str__(self):
        return self.username


# ===============================
# MEMBERSHIP: USER - COMPANY - ROLE
# ===============================
class Membership(models.Model):
    """
    Một user có thể thuộc nhiều company.
    Mỗi company có role khác nhau.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="memberships"
    )

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="members"
    )

    role = models.CharField(
        max_length=50,
        choices=ROLE_CHOICES
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "company")
        verbose_name = "Phân quyền công ty"
        verbose_name_plural = "Phân quyền công ty"

    def __str__(self):
        return f"{self.user.username} - {self.company.name} ({self.role})"