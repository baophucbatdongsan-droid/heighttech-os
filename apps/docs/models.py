from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class Document(models.Model):
    TYPE_DOC = "doc"
    TYPE_PROPOSAL = "proposal"
    TYPE_QUOTATION = "quotation"
    TYPE_CONTRACT = "contract"
    TYPE_APPENDIX = "appendix"
    TYPE_REPORT = "report"

    TYPE_CHOICES = (
        (TYPE_DOC, "Doc"),
        (TYPE_PROPOSAL, "Proposal"),
        (TYPE_QUOTATION, "Quotation"),
        (TYPE_CONTRACT, "Contract"),
        (TYPE_APPENDIX, "Appendix"),
        (TYPE_REPORT, "Report"),
    )

    tenant_id = models.BigIntegerField(db_index=True)

    title = models.CharField(max_length=500)
    doc_type = models.CharField(
        max_length=50,
        choices=TYPE_CHOICES,
        default=TYPE_DOC,
        db_index=True,
    )

    linked_target_type = models.CharField(max_length=100, blank=True, default="", db_index=True)
    linked_target_id = models.BigIntegerField(null=True, blank=True, db_index=True)

    content_html = models.TextField(blank=True, default="")
    public_token = models.CharField(max_length=120, blank=True, default="", db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="docs_created",
    )

    is_deleted = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "docs_document"
        ordering = ("-id",)
        indexes = [
            models.Index(fields=["tenant_id", "doc_type"]),
            models.Index(fields=["tenant_id", "linked_target_type", "linked_target_id"]),
        ]

    def save(self, *args, **kwargs):
        if not self.public_token:
            self.public_token = uuid.uuid4().hex
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.title or f"Document #{self.pk}"