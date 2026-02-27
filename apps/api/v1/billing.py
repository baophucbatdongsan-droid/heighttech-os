# apps/api/v1/billing.py
from __future__ import annotations

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from django.utils import timezone

from apps.billing.models import Invoice
from apps.billing.metering import get_usage_value
from apps.billing.services.payment import mark_invoice_paid


class BillingOverviewAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = getattr(request, "tenant", None)
        if not tenant:
            return Response({"detail": "Tenant missing"}, status=400)

        today = timezone.localdate()

        return Response({
            "tenant": {
                "id": tenant.id,
                "name": tenant.name,
                "plan": tenant.plan,
                "status": tenant.status,
            },
            "today_usage": {
                "requests": int(get_usage_value(tenant.id, today, "requests") or 0),
                "errors": int(get_usage_value(tenant.id, today, "errors") or 0),
                "slow": int(get_usage_value(tenant.id, today, "slow") or 0),
                "rate_limited": int(get_usage_value(tenant.id, today, "rate_limited") or 0),
            }
        })