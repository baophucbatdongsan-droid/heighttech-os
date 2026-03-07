# apps/api/urls.py
from django.urls import include, path

from .views import ApiRoot
from .views_health import health_view

app_name = "api"

urlpatterns = [
    path("", ApiRoot.as_view(), name="api-root"),
    path("health/", health_view, name="api-health"),
    path("v1/", include("apps.api.v1.urls")),
]