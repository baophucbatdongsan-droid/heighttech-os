from apps.tenants.models import Tenant
from apps.core.tenant_context import set_current_tenant

set_current_tenant(Tenant.objects.get(id=1))
print("✅ Tenant context ready (tenant_id=1)")