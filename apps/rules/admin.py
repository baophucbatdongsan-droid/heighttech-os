from django.contrib import admin
from .models import RuleDecisionLog, RuleRelease


@admin.register(RuleDecisionLog)
class RuleDecisionLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "rule_key",
        "industry_code",
        "rule_version",
        "tenant_id",
        "shop_id",
        "created_at",
    )
    list_filter = ("industry_code", "rule_version", "rule_key")
    search_fields = ("request_id",)
    readonly_fields = ("created_at",)
    ordering = ("-id",)


@admin.register(RuleRelease)
class RuleReleaseAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "industry_code",
        "rule_version",
        "effective_from",
        "is_enabled",
        "created_at",
        "notes",
    )
    list_filter = ("industry_code", "rule_version", "is_enabled")
    search_fields = ("notes",)
    ordering = ("-effective_from", "-id")