# apps/core/mixins.py
from __future__ import annotations

from typing import Iterable

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

from apps.core.authz import get_actor_ctx, has_any_role


class RoleRequiredMixin(LoginRequiredMixin):
    """
    Base mixin: yêu cầu login + role thuộc allowed_roles.
    Role lấy từ get_actor_ctx(request) để thống nhất toàn hệ thống.
    """
    allowed_roles: Iterable[str] = ()

    def dispatch(self, request, *args, **kwargs):
        # LoginRequiredMixin sẽ redirect nếu chưa login
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)

        ctx = get_actor_ctx(request)

        # ✅ admin/staff luôn bypass (tránh 403 do role mismatch)
        if getattr(request.user, "is_superuser", False) or getattr(request.user, "is_staff", False):
            return super().dispatch(request, *args, **kwargs)

        # ✅ nếu có allowed_roles thì check role
        if self.allowed_roles:
            role = getattr(ctx, "role", None) or getattr(request, "role", None) or ""
            if not has_any_role(role, self.allowed_roles):
                raise PermissionDenied("You do not have permission.")

        return super().dispatch(request, *args, **kwargs)


class FounderRequiredMixin(RoleRequiredMixin):
    """
    Founder console: founder + admin.
    Admin/staff bypass sẵn ở RoleRequiredMixin.
    """
    allowed_roles = ("founder", "admin")