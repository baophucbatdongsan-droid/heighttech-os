from __future__ import annotations

from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView

from apps.core.tenant_context import get_request_tenant_id


class TenantRequiredAPIView(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)

        tenant_id = get_request_tenant_id(request)
        if not tenant_id:
            raise ValidationError("Tenant context missing")

        request.current_tenant_id = int(tenant_id)