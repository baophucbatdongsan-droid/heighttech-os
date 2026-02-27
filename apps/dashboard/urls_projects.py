# apps/dashboard/urls_projects.py
from django.urls import path

from apps.dashboard.views_projects_page import (
    projects_dashboard_page,
    projects_dashboard_export_csv,
    projects_dashboard_bulk_update,
)
from apps.dashboard import views_projects

app_name = "dashboard_projects"

urlpatterns = [
    path("projects/", projects_dashboard_page, name="projects_dashboard"),
    path("projects/export.csv", projects_dashboard_export_csv, name="projects_dashboard_export_csv"),
    path("projects/bulk-update/", projects_dashboard_bulk_update, name="projects_dashboard_bulk_update"),
    path("projects/<int:project_id>/", views_projects.project_detail, name="project_detail"),
]