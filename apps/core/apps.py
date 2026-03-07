# apps/core/apps.py
from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"

    def ready(self):
        """
        Register signals cho app core.
        Lưu ý:
        - Tuyệt đối không khai báo 2 CoreConfig hoặc 2 ready() vì sẽ bị đăng ký signal 2 lần.
        """

        # 1) Signal hệ thống cũ (nếu bạn còn dùng)
        # Nếu không dùng nữa thì comment / xoá dòng này.
        try:
            import apps.core.signals  # noqa: F401
        except Exception:
            pass

        # 2) Audit signals (mới)
        try:
            import apps.core.audit_signals  # noqa: F401
        except Exception:
            pass

    # apps/core/apps.py (thêm vào ready)
    def ready(self):
        try:
            from apps.events import setup_event_handlers
            setup_event_handlers()
        except Exception:
            pass