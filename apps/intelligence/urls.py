from __future__ import annotations

from django.urls import path
from .views import founder_dashboard, founder_shop_detail

app_name = "intelligence"

urlpatterns = [
    # ✅ tránh đụng /founder/ của dashboard
    path("intelligence/founder/", founder_dashboard, name="founder_dashboard"),
    path("intelligence/founder/shop/<int:shop_id>/", founder_shop_detail, name="founder_shop_detail"),
]