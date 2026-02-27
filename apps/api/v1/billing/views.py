from __future__ import annotations

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView

from apps.billing.metering import get_usage_value
from apps.billing.models import Invoice

from apps.billing.models import Invoice, TenantUsageDaily, TenantUsageMonthly

class BillingOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = getattr(request, "tenant", None)
        tenant_id = getattr(request, "tenant_id", None) or (tenant.id if tenant else None)

        d = timezone.localdate()
        data = {
            "tenant_id": tenant_id,
            "plan": getattr(tenant, "plan", None) if tenant else None,
            "status": getattr(tenant, "status", None) if tenant else None,
            "today": d.isoformat(),
            "usage_today": {
                "requests": int(get_usage_value(tenant_id, d, "requests") or 0),
                "errors": int(get_usage_value(tenant_id, d, "errors") or 0),
                "slow": int(get_usage_value(tenant_id, d, "slow") or 0),
                "rate_limited": int(get_usage_value(tenant_id, d, "rate_limited") or 0),
            },
        }
        return Response(data)


class InvoiceListView(ListAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, "tenant", None)
        return Invoice.objects.filter(tenant=tenant).order_by("-year", "-month")


class InvoiceDetailView(RetrieveAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, "tenant", None)
        return Invoice.objects.filter(tenant=tenant)



class BillingOverviewAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        tenant = getattr(request, "tenant", None)
        tenant_id = getattr(request, "tenant_id", None) or getattr(tenant, "id", None)

        if not tenant_id:
            return Response({"detail": "Tenant not resolved"}, status=400)

        today = timezone.localdate()
        ym = (today.year, today.month)

        # daily today
        daily = (
            TenantUsageDaily.objects.filter(tenant_id=tenant_id, date=today)
            .values("date", "requests", "errors", "slow", "rate_limited")
            .first()
        )

        # monthly current month (nếu bạn đang dùng year/month int)
        monthly = (
            TenantUsageMonthly.objects.filter(tenant_id=tenant_id, year=ym[0], month=ym[1])
            .values("year", "month", "period_start", "period_end", "requests", "errors", "slow", "rate_limited")
            .first()
        )

        # latest invoice
        inv = (
            Invoice.objects.filter(tenant_id=tenant_id)
            .order_by("-year", "-month", "-id")
            .values("id", "year", "month", "total_amount", "currency", "status", "period_start", "period_end")
            .first()
        )

        return Response(
            {
                "tenant_id": int(tenant_id),
                "today": str(today),
                "daily": daily or {"date": str(today), "requests": 0, "errors": 0, "slow": 0, "rate_limited": 0},
                "monthly": monthly,
                "latest_invoice": inv,
            }
        )