# apps/dashboard/views_founder.py
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from apps.core.authz import get_actor_ctx, has_any_role


@login_required
def founder_home(request):
    """
    Founder console home.
    Rule:
      - superuser/staff: luôn vào
      - role founder/admin: vào
      - còn lại: 403
    """
    user = request.user
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return render(request, "founder/home.html", {})

    ctx = get_actor_ctx(request)
    role = (getattr(ctx, "role", None) or getattr(request, "role", None) or "").lower()

    if not has_any_role(role, ("founder", "admin")):
        raise PermissionDenied("You do not have permission.")

    return render(request, "founder/home.html", {})