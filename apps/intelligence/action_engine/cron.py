from django.apps import apps
from .engine import ActionEngine


def run_all_tenants():

    Tenant = apps.get_model("tenants", "Tenant")

    for tenant in Tenant.objects.all():

        engine = ActionEngine(tenant.id)

        alerts = engine.run()

        print("Tenant:", tenant.id, "alerts:", len(alerts))