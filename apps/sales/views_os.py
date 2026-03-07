# FILE: apps/sales/views_os.py
from __future__ import annotations

from typing import Optional

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest
from django.shortcuts import redirect, render

from apps.core.decorators import require_ability
from apps.core.policy import VIEW_DASHBOARD


def _tenant_id(request: HttpRequest) -> Optional[int]:
    """
    Resolve tenant_id from (priority):
    1) request.tenant_id (middleware)
    2) session keys
    """
    tid = getattr(request, "tenant_id", None)
    try:
        if tid:
            return int(tid)
    except Exception:
        pass

    for k in ("tenant_id", "active_tenant_id", "current_tenant_id"):
        try:
            v = request.session.get(k)
            if v:
                return int(v)
        except Exception:
            continue

    return None


@login_required
@require_ability(VIEW_DASHBOARD)
def sales_home(request: HttpRequest):
    """
    HeightTech OS Control Center (Sales entry)
    - Render unified OS UI (Stripe-like)
    - FE will call /api/v1/os/control-center/ + notifications + timeline
    """
    tid = _tenant_id(request)
    if not tid:
        return redirect("/dashboard/")

    # ✅ NEW: use unified OS UI template
    return render(
        request,
        "os/control_center.html",
        {
            "tid": tid,
            "me": request.user,
        },
    )