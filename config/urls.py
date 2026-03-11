from __future__ import annotations

from django.contrib import admin
from django.shortcuts import redirect, render
from django.urls import include, path

from apps.core.views_metrics import metrics_view


admin.site.site_header = "HeightTech OS"
admin.site.site_title = "HeightTech OS"
admin.site.index_title = "Bảng điều hành hệ thống HeightTech"


def root_view(request):
    user = getattr(request, "user", None)

    if user and getattr(user, "is_authenticated", False):
        return redirect("/os/")

    return render(request, "auth/root_landing.html")


urlpatterns = [
    path("", root_view),
    path("admin/", admin.site.urls),

    path("", include("apps.accounts.urls_auth")),
    path("", include("apps.core.urls")),
    path("", include("apps.intelligence.urls")),

    path("app/", include("apps.dashboard.urls_app")),

    path(
        "dashboard/",
        include(
            ("apps.dashboard.urls_projects", "dashboard_projects"),
            namespace="dashboard_projects",
        ),
    ),
    path("dashboard/", include("apps.dashboard.urls")),
    path("founder/", include("apps.dashboard.urls_founder")),

    path("api/", include("apps.api.urls")),
    path("metrics/", metrics_view),

    path("sales/", include(("apps.sales.urls", "sales"), namespace="sales")),

    # OS + Work
    path("", include(("apps.os.urls", "os"), namespace="os")),
]