from __future__ import annotations

from django.urls import path
from apps.dashboard import views_workspace

app_name = "workspace"

urlpatterns = [
    path("", views_workspace.app_home, name="app_home"),
    path("select/", views_workspace.select_workspace, name="select_workspace"),
    path("switch/", views_workspace.switch_workspace, name="switch_workspace"),
]