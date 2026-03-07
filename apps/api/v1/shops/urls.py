# apps/api/v1/shops/urls.py
from __future__ import annotations

from django.urls import path

from .views_dashboard import ShopDashboardView

app_name = "shops"

urlpatterns = [
    path("<int:shop_id>/dashboard/", ShopDashboardView.as_view(), name="shop_dashboard"),
]