# FILE: apps/sales/urls.py
from django.urls import path
from .views_os import sales_home

app_name = "sales"

urlpatterns = [
    path("", sales_home, name="sales_home"),
]