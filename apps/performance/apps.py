# apps/performance/apps.py
from django.apps import AppConfig

class PerformanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.performance"
    label = "performance"

    def ready(self):
        from . import signals  # noqa