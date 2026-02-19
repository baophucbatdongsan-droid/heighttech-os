from __future__ import annotations

from django.apps import AppConfig


class ShopsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.shops"

    def ready(self):
        from . import signals  # noqa