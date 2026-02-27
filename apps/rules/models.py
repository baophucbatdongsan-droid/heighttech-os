

from django.db import models
from django.utils import timezone


class RuleRelease(models.Model):
    """
    Founder control: enable/disable rule_version theo industry.
    DB chỉ giữ metadata release, core logic vẫn nằm trong code.
    """

    industry_code = models.CharField(max_length=64, db_index=True)
    rule_version = models.CharField(max_length=32, db_index=True)

    effective_from = models.DateField(db_index=True)
    is_enabled = models.BooleanField(default=True, db_index=True)

    notes = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["industry_code", "rule_version", "is_enabled", "effective_from"], name="idx_rule_release"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["industry_code", "rule_version", "effective_from"],
                name="uq_rule_release_industry_version_effective",
            )
        ]

    def __str__(self) -> str:
        status = "ENABLED" if self.is_enabled else "DISABLED"
        return f"{self.industry_code}@{self.rule_version} ({self.effective_from}) {status}"


class RuleDecisionLog(models.Model):
    """
    Audit decisions của engine: replay được.
    """
    tenant_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    shop_id = models.BigIntegerField(null=True, blank=True, db_index=True)

    industry_code = models.CharField(max_length=64, db_index=True)
    rule_version = models.CharField(max_length=32, db_index=True)

    rule_key = models.CharField(max_length=128, db_index=True)  # vd: "commission.calculate"
    request_id = models.CharField(max_length=64, blank=True, default="")

    input_snapshot = models.JSONField(default=dict)
    output_result = models.JSONField(default=dict)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["industry_code", "rule_version", "rule_key", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.rule_key} {self.industry_code}@{self.rule_version} ({self.created_at})"