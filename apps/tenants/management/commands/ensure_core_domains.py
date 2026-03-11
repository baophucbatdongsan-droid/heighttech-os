from django.core.management.base import BaseCommand
from apps.tenants.models import TenantDomain


CORE_DOMAINS = [
    "app.heighttech.vn",
    "api.heighttech.vn",
    "staging.heighttech.vn",
]


class Command(BaseCommand):

    help = "Ensure core hub domains exist"

    def handle(self, *args, **kwargs):

        for d in CORE_DOMAINS:

            obj, created = TenantDomain.objects.update_or_create(
                domain=d,
                defaults={
                    "tenant_id": 1,
                    "is_active": True,
                }
            )

            status = "CREATED" if created else "UPDATED"

            print(status, d, "-> tenant", obj.tenant_id)