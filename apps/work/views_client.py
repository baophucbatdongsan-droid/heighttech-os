# FILE: apps/work/views_client.py
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Optional

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.core.decorators import require_ability
from apps.core.policy import VIEW_DASHBOARD
from apps.work.models import WorkItem


def _tenant_id(request: HttpRequest) -> Optional[int]:
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
            pass
    return None


@login_required
@require_ability(VIEW_DASHBOARD)
def client_work_home(request: HttpRequest):
    """
    Client view:
    - only visible_to_client=True
    - optional filter by shop
    """
    tid = _tenant_id(request)
    if not tid:
        return redirect("/dashboard/")

    qs = WorkItem.objects.filter(tenant_id=tid, visible_to_client=True)

    shop_id = (request.GET.get("shop") or "").strip()
    if shop_id:
        try:
            qs = qs.filter(shop_id=int(shop_id))
        except Exception:
            pass

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))

    now = timezone.now()
    last_30d = now - timedelta(days=30)

    items = (
        qs.select_related("assignee", "shop")
        .only("id", "title", "status", "priority", "due_at", "assignee__username", "shop_id", "type", "updated_at")
        .order_by("-updated_at")[:400]
    )

    context: Dict[str, Any] = {
        "tid": tid,
        "items": items,
        "q": q,
        "shop": shop_id,
        "now": now,
        "last_30d": last_30d,
    }
    return render(request, "work/client_work_home.html", context)