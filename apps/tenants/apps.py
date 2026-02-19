# apps/tenants/apps.py
from django.apps import AppConfig

class TenantsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tenants"
    label = "tenants"  # ✅ cực quan trọng để "tenants.Tenant" match