from __future__ import annotations

from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin

SESSION_ACTIVE_SHOP_ID = "active_shop_id"

ALLOW_PREFIXES = (
    "/login/",
    "/register/",
    "/logout/",
    "/admin/",
    "/static/",
    "/media/",
    "/metrics/",
    "/favicon.ico",
    "/os/",
    "/work/",
    "/sales/",
    "/app/",
    "/api/",
)


class WorkspaceRequiredMiddleware(MiddlewareMixin):
    """
    Nếu user đã login mà chưa chọn shop => ép về /app/select/
    Nhưng chỉ ép ở các route dashboard/founder thật sự cần workspace.
    Không chặn os/admin/api/login/static/media...
    """

    def process_request(self, request):
        path = request.path or "/"

        if path == "/":
            return None

        if any(path.startswith(p) for p in ALLOW_PREFIXES):
            return None

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None

        needs_workspace = (
            path.startswith("/dashboard/") or
            path.startswith("/founder/")
        )

        if not needs_workspace:
            return None

        if not request.session.get(SESSION_ACTIVE_SHOP_ID):
            if path != "/app/select/":
                return redirect("/app/select/")

        return None