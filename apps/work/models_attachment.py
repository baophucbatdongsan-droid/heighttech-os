from __future__ import annotations

import mimetypes
import os

from django.conf import settings
from django.db import models


def task_attachment_upload_to(instance, filename: str) -> str:
    tenant_id = getattr(instance, "tenant_id", "") or "unknown"
    task_id = getattr(instance, "task_id", "") or "unknown"
    return f"work/task_attachments/tenant_{tenant_id}/task_{task_id}/{filename}"


class TaskAttachment(models.Model):
    task = models.ForeignKey(
        "work.WorkItem",
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    tenant_id = models.BigIntegerField(db_index=True)

    company_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    shop_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    project_id = models.BigIntegerField(null=True, blank=True, db_index=True)

    target_type = models.CharField(max_length=64, blank=True, default="")
    target_id = models.BigIntegerField(null=True, blank=True, db_index=True)

    file = models.FileField(upload_to=task_attachment_upload_to)

    file_name = models.CharField(max_length=255, blank=True, default="")
    original_name = models.CharField(max_length=255, blank=True, default="")
    content_type = models.CharField(max_length=255, blank=True, default="")
    file_size = models.BigIntegerField(default=0)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="task_attachments_uploaded",
    )

    is_deleted = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "work_task_attachment"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["tenant_id", "task"]),
            models.Index(fields=["tenant_id", "shop_id"]),
            models.Index(fields=["tenant_id", "project_id"]),
            models.Index(fields=["tenant_id", "is_deleted"]),
            models.Index(fields=["tenant_id", "target_type", "target_id"]),
        ]

    def __str__(self) -> str:
        return self.original_name or self.file_name or f"Attachment #{self.pk}"

    def hydrate_context_from_task(self):
        task = getattr(self, "task", None)
        if not task:
            return

        try:
            self.tenant_id = int(getattr(task, "tenant_id", None) or getattr(task, "tenant_id_id", None) or self.tenant_id or 0)
        except Exception:
            pass

        self.company_id = getattr(task, "company_id", None)
        self.shop_id = getattr(task, "shop_id", None)
        self.project_id = getattr(task, "project_id", None)

        self.target_type = str(getattr(task, "target_type", "") or "")
        self.target_id = getattr(task, "target_id", None)

    def save(self, *args, **kwargs):
        if self.task_id:
            self.hydrate_context_from_task()

        if self.file:
            base_name = os.path.basename(getattr(self.file, "name", "") or "")
            if not self.file_name:
                self.file_name = base_name
            if not self.original_name:
                self.original_name = base_name

            try:
                self.file_size = int(getattr(self.file, "size", 0) or 0)
            except Exception:
                pass

            if not self.content_type:
                guessed, _ = mimetypes.guess_type(base_name)
                self.content_type = guessed or ""

        super().save(*args, **kwargs)