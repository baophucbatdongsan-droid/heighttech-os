from __future__ import annotations

from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path

from apps.core.views_metrics import metrics_view
from apps.work.views_client import client_work_home
from apps.sales.views_client_sales import client_sales_home
from django.views.generic import TemplateView
from django.http import HttpResponse

def root_view(request):
    """
    Root điều hướng theo trạng thái đăng nhập + role.
    - Chưa login: /login/
    - Đã login:
        founder/admin -> /founder/
        còn lại       -> /dashboard/
    """
    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        role = getattr(request, "role", None) or (
            "admin" if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False) else "operator"
        )
        if str(role).lower() in ("founder", "admin"):
            return redirect("/founder/")
        return redirect("/dashboard/")
    return redirect("/login/")


urlpatterns = [
    path("", root_view),
    path("admin/", admin.site.urls),

    # core misc (healthz...)
    path("", include("apps.core.urls")),

    # login/logout legacy (đang ở intelligence) -> giữ /login/ để khỏi gãy
    path("", include("apps.intelligence.urls")),

    # workspace
    path("app/", include("apps.dashboard.urls_app")),

    # dashboards
    path(
        "dashboard/",
        include(("apps.dashboard.urls_projects", "dashboard_projects"), namespace="dashboard_projects"),
    ),
    path("dashboard/", include("apps.dashboard.urls")),

    # founder
    path("founder/", include("apps.dashboard.urls_founder")),

    # api
    path("api/", include("apps.api.urls")),

    # metrics
    path("metrics/", metrics_view),

    # add this line somewhere in urlpatterns
    path("work/", include(("apps.work.urls", "work"), namespace="work")),

    path("client/work/", client_work_home),
    path("client/sales/", client_sales_home),

    path("sales/", include("apps.sales.urls", namespace="sales")),

    # ✅ OS UI (Stripe-like)
    path("os/", TemplateView.as_view(template_name="os/index.html"), name="os_ui"),

]
