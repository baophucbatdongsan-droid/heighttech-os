from django.urls import include, path
from .views import dashboard_view

urlpatterns = [
    path("", dashboard_view, name="dashboard"),

    # projects pages
    path("", include("apps.dashboard.urls_projects")),
]