# apps/intelligence/apps.py
from __future__ import annotations

import os
import logging
from django.apps import AppConfig

logger = logging.getLogger(__name__)


class IntelligenceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.intelligence"
    label = "intelligence"

    def ready(self):
        """
        FINAL:
        - Tránh double-register khi runserver autoreload.
        - Setup handlers an toàn (không crash nếu có lỗi import tạm thời).
        """
        # Django runserver autoreload chạy 2 process, chỉ chạy ở process thật
        if os.environ.get("RUN_MAIN") != "true":
            return

        try:
            from apps.intelligence.events_handlers import setup_handlers
            setup_handlers()
        except Exception:
            logger.exception("IntelligenceConfig.ready(): setup_handlers failed")