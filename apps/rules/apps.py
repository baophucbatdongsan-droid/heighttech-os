# apps/rules/apps.py
from __future__ import annotations

from django.apps import AppConfig


class RulesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.rules"
    verbose_name = "Rules"

    def ready(self):
        # Import policies package so @register decorators run and engines are registered.
        import apps.rules.policies  # noqa: F401