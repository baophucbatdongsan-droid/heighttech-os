# apps/os/apps.py
from django.apps import AppConfig


class OSConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.os"
    label = "os"