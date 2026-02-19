# config/urls.py
from django.contrib import admin
from django.urls import path, include
from apps.intelligence.views import founder_dashboard

urlpatterns = [
    path("admin/", admin.site.urls),

    # ✅ login/logout
    path("", include("apps.core.urls")),

    path("dashboard/", include("apps.dashboard.urls")),
    path("founder/", founder_dashboard, name="founder_dashboard"),

    path("api/", include("apps.api.urls")),
    path("", include("apps.intelligence.urls")),
]