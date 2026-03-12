from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from apps.accounts.models import Membership
from apps.sheets.models import Sheet


def _current_tenant_id(request):
    user = getattr(request, "user", None)

    try:
        if user and user.is_authenticated:
            m = (
                Membership.objects.filter(user=user, is_active=True)
                .order_by("id")
                .first()
            )
            if m and m.tenant_id:
                return int(m.tenant_id)
    except Exception:
        pass

    tenant = getattr(request, "tenant", None)
    tenant_id = getattr(tenant, "id", None) if tenant else None
    if tenant_id:
        try:
            return int(tenant_id)
        except Exception:
            pass

    tenant_id = getattr(request, "tenant_id", None)
    if tenant_id:
        try:
            return int(tenant_id)
        except Exception:
            pass

    return None


@login_required
def sheets_page(request):
    tenant_id = _current_tenant_id(request)
    if not tenant_id:
        raise Http404("Không xác định được tenant hiện tại")

    return render(
        request,
        "os/sheets_list.html",
        {
            "current_tenant_id": tenant_id,
        },
    )


@login_required
def sheet_detail_page(request, sheet_id: int):
    tenant_id = _current_tenant_id(request)
    if not tenant_id:
        raise Http404("Không xác định được tenant hiện tại")

    obj = (
        Sheet.objects.filter(
            id=int(sheet_id),
            tenant_id=int(tenant_id),
            is_deleted=False,
        )
        .first()
    )
    if not obj:
        raise Http404("Sheet không tồn tại trong tenant hiện tại")

    return render(
        request,
        "os/sheet_detail.html",
        {
            "current_tenant_id": tenant_id,
            "sheet_id": int(obj.id),
        },
    )