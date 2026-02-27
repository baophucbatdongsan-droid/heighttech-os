from __future__ import annotations

from django.apps import AppConfig


class RulesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.rules"
    verbose_name = "Rules"

    def ready(self):
        # Import registry để nó tự register rules khi Django boot
        # (tránh import lung tung ở module level gây vòng import)
        from . import registry  # noqa: F401s
        from .policies import v1_default  # noqa