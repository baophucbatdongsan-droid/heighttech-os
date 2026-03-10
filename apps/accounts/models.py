from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


ROLE_FOUNDER = "founder"
ROLE_HEAD = "head"  # legacy
ROLE_LEADER_CHANNEL = "leader_channel"
ROLE_LEADER_BOOKING = "leader_booking"
ROLE_LEADER_OPERATION = "leader_operation"
ROLE_ACCOUNT = "account"
ROLE_SALE = "sale"
ROLE_OPERATOR = "operator"
ROLE_EDITOR = "editor"

ROLE_CHOICES = (
    (ROLE_FOUNDER, "Founder"),
    (ROLE_HEAD, "Head (Legacy)"),
    (ROLE_LEADER_CHANNEL, "Leader Channel"),
    (ROLE_LEADER_BOOKING, "Leader Booking"),
    (ROLE_LEADER_OPERATION, "Leader Operation"),
    (ROLE_ACCOUNT, "Account"),
    (ROLE_SALE, "Sale"),
    (ROLE_OPERATOR, "Operator"),
    (ROLE_EDITOR, "Editor"),
)


class User(AbstractUser):
    """
    Giữ username để tránh vỡ code cũ.
    Login ngoài giao diện bằng email.
    """
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Nhân sự"
        verbose_name_plural = "Nhân sự"

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.email or self.username


class Membership(models.Model):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="memberships",
        db_index=True,
    )

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
            models.UniqueConstraint(
                fields=["tenant", "user", "company"],
                name="uq_mship_t_u_c",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant"], name="msh_t_idx"),
            models.Index(fields=["user", "is_active"], name="msh_u_act_idx"),
            models.Index(fields=["company", "is_active"], name="msh_c_act_idx"),
            models.Index(fields=["tenant", "company", "is_active"], name="msh_t_co_act_idx"),
            models.Index(fields=["role"], name="msh_role_idx"),
        ]

    def save(self, *args, **kwargs):
        if not getattr(self, "tenant_id", None) and getattr(self, "company_id", None):
            try:
                self.tenant_id = self.company.tenant_id
            except Exception:
                pass
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        user_label = self.user.email or self.user.username
        return f"{user_label} - {self.company.name} ({self.role})"


from .models_invite import InviteCode  # noqa: F401