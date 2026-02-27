# apps/work/models.py
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.managers import TenantAllManager, TenantManager


class WorkItem(models.Model):
    """
    Task/Work item cho hệ điều hành:
    - 2 chiều: nội bộ (agency/company) + chủ shop (client/owner)
    - Target generic: target_type + target_id (shop/channel/booking/brand/company/project...)
    """

    class Status(models.TextChoices):
        TODO = "todo", "Todo"
        DOING = "doing", "Doing"
        BLOCKED = "blocked", "Blocked"
        DONE = "done", "Done"
        CANCELLED = "cancelled", "Cancelled"

    class Priority(models.IntegerChoices):
        LOW = 1, "Low"
        NORMAL = 2, "Normal"
        HIGH = 3, "High"
        URGENT = 4, "Urgent"

    # ===== Multi-tenant =====
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="work_items",
        db_index=True,
    )

    # ===== Scope optional =====
    company = models.ForeignKey(
        "companies.Company",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="work_items",
        db_index=True,
    )

    project = models.ForeignKey(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="work_items",
        db_index=True,
    )

    # ===== Generic target =====
    # ví dụ:
    # - target_type="shop", target_id=123
    # - target_type="channel", target_id=77
    # - target_type="booking", target_id=9
    target_type = models.CharField(max_length=50, blank=True, default="", db_index=True)
    target_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)

    # ===== Core fields =====
    title = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True, default="")

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.TODO,
        db_index=True,
    )

    priority = models.PositiveSmallIntegerField(
        choices=Priority.choices,
        default=Priority.NORMAL,
        db_index=True,
    )

    # ✅ Kanban ordering (kéo thả)
    position = models.PositiveIntegerField(default=0, db_index=True)

    tags = models.JSONField(default=list, blank=True)  # ["tiktok", "ads", "creative"]

    due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    done_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # ✅ Portal 2 chiều: Ẩn với khách nếu bật
    is_internal = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Nếu bật: chỉ nội bộ thấy, khách hàng không thấy",
    )

    # ===== People =====
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="work_items_created",
    )

    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="work_items_assigned",
        db_index=True,
    )

    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="work_items_requested",
        db_index=True,
        help_text="Người yêu cầu (có thể là chủ shop/client)",
    )

    # ===== Audit =====
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        ordering = ["-id"]
        # NOTE: SQLite giới hạn tên index <= 30 ký tự.
        indexes = [
            models.Index(fields=["tenant", "status"], name="wi_t_st_idx"),
            models.Index(fields=["tenant", "priority"], name="wi_t_pri_idx"),
            models.Index(fields=["tenant", "company"], name="wi_t_co_idx"),
            models.Index(fields=["tenant", "project"], name="wi_t_pj_idx"),
            models.Index(fields=["tenant", "target_type", "target_id"], name="wi_t_tg_idx"),
            models.Index(fields=["tenant", "assignee", "status"], name="wi_t_as_st_idx"),
            # ✅ để sort theo cột kanban nhanh
            models.Index(fields=["tenant", "status", "position"], name="wi_t_sp_idx"),
            # ✅ lọc nhanh việc internal/public theo tenant
            models.Index(fields=["tenant", "is_internal"], name="wi_t_int_idx"),
        ]

    def save(self, *args, **kwargs):
        # auto sync tenant từ company/project nếu thiếu
        if not self.tenant_id:
            if self.project_id:
                try:
                    self.tenant_id = self.project.tenant_id
                except Exception:
                    pass
            if (not self.tenant_id) and self.company_id:
                try:
                    self.tenant_id = self.company.tenant_id
                except Exception:
                    pass

        # auto timestamps by status
        if self.status == self.Status.DOING and not self.started_at:
            self.started_at = timezone.now()

        if self.status in (self.Status.DONE, self.Status.CANCELLED) and not self.done_at:
            self.done_at = timezone.now()

        if self.status not in (self.Status.DONE, self.Status.CANCELLED):
            # nếu reopen
            self.done_at = None

        super().save(*args, **kwargs)

    def __str__(self) -> str:
        t = f"{self.target_type}:{self.target_id}" if self.target_type and self.target_id else "-"
        return f"[{self.status}] {self.title} ({t})"


class WorkComment(models.Model):
    """
    Comment / nhật ký update cho WorkItem.
    (Sau này có thể tách event log riêng, hiện tại đủ dùng)
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="work_comments",
        db_index=True,
    )

    work_item = models.ForeignKey(
        "work.WorkItem",
        on_delete=models.CASCADE,
        related_name="comments",
        db_index=True,
    )

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="work_comments",
    )

    body = models.TextField(blank=True, default="")
    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["tenant", "work_item"], name="wc_t_wi_idx"),
            models.Index(fields=["tenant", "created_at"], name="wc_t_ct_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self.tenant_id and self.work_item_id:
            try:
                self.tenant_id = self.work_item.tenant_id
            except Exception:
                pass
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Comment#{self.pk} item={self.work_item_id}"