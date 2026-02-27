# apps/api/v1/billing/urls.py
from __future__ import annotations

from django.urls import path

from .views import (
    BillingOverviewView,
    InvoiceListView,
    InvoiceDetailView,
    BillingOverviewAPI,
)

app_name = "billing"

urlpatterns = [
    # HTML pages
    path("overview/", BillingOverviewView.as_view(), name="overview"),
    path("invoices/", InvoiceListView.as_view(), name="invoices"),
    path("invoices/<int:pk>/", InvoiceDetailView.as_view(), name="invoice-detail"),

    # API endpoints (tách namespace để không đè route)
    path("api/overview/", BillingOverviewAPI.as_view(), name="api-overview"),
]