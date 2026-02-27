# apps/intelligence/urls.py
from django.urls import path
from .views import founder_dashboard, founder_shop_detail

app_name = "intelligence"

urlpatterns = [
    path("founder/", founder_dashboard, name="founder_dashboard"),
    path("founder/shop/<int:shop_id>/", founder_shop_detail, name="founder_shop_detail"),
]