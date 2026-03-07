from django.urls import path
from apps.dashboard.views_founder import founder_home

urlpatterns = [
    path("", founder_home, name="founder_home"),
]