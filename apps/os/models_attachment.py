from __future__ import annotations

import mimetypes
import os

from django.conf import settings
from django.db import models


def os_attachment_upload_to(instance, filename: str) -> str:
    tenant_id = getattr(instance, "tenant_id", "") or "unknown"
    target_type = getattr(instance, "target_type", "") or "unknown"
    target_id = getattr(instance, "target_id", "") or "unknown"
    return f"os/attachments/tenant_{tenant_id}/{target_type}/{target_id}/{filename}"


class OSAttachment(models.Model):
    TARGET_CONTRACT = "contract"
    TARGET_CHANNEL_CONTENT = "channel_content"

    TARGET_CHOICES = (
        (TARGET_CONTRACT, "Contract"),
        (TARGET_CHANNEL_CONTENT, "Channel Content"),
    )

    tenant_id = models.BigIntegerField(db_index=True)

    target_type = models.CharField(max_length=64, choices=TARGET_CHOICES, db_index=True)
    target_id = models.BigIntegerField(db_index=True)

    contract_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    channel_content_id = models.BigIntegerField(null=True, blank=True, db_index=True)

    company_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    shop_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    project_id = models.BigIntegerField(null=True, blank=True, db_index=True)

    file = models.FileField(upload_to=os_attachment_upload_to)

    file_name = models.CharField(max_length=255, blank=True, default="")
    original_name = models.CharField(max_length=255, blank=True, default="")
    content_type = models.CharField(max_length=255, blank=True, default="")
    file_size = models.BigIntegerField(default=0)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="os_attachments_uploaded",
    )

    is_deleted = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "os_attachment"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["tenant_id", "target_type", "target_id"]),
            models.Index(fields=["tenant_id", "contract_id"]),
            models.Index(fields=["tenant_id", "channel_content_id"]),
            models.Index(fields=["tenant_id", "shop_id"]),
            models.Index(fields=["tenant_id", "project_id"]),
            models.Index(fields=["tenant_id", "is_deleted"]),
        ]

    def __str__(self) -> str:
        return self.original_name or self.file_name or f"OSAttachment #{self.pk}"

    def save(self, *args, **kwargs):
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

        if self.target_type == self.TARGET_CONTRACT and self.target_id and not self.contract_id:
            self.contract_id = int(self.target_id)

        if self.target_type == self.TARGET_CHANNEL_CONTENT and self.target_id and not self.channel_content_id:
            self.channel_content_id = int(self.target_id)

        super().save(*args, **kwargs)