from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from apps.accounts.models import Membership
from apps.contracts.models import Contract


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
def contracts_page(request):
    tenant_id = _current_tenant_id(request)
    if not tenant_id:
        raise Http404("Không xác định được tenant hiện tại")

    return render(
        request,
        "os_contracts.html",
        {
            "current_tenant_id": tenant_id,
        },
    )


@login_required
def contract_detail_page(request, contract_id: int):
    tenant_id = _current_tenant_id(request)
    if not tenant_id:
        raise Http404("Không xác định được tenant hiện tại")

    obj = Contract.objects_all.filter(
        id=int(contract_id),
        tenant_id=int(tenant_id),
    ).first()

    if not obj:
        raise Http404("Hợp đồng không tồn tại trong tenant hiện tại")

    return render(
        request,
        "os_contract_detail.html",
        {
            "current_tenant_id": tenant_id,
            "contract_id": int(obj.id),
        },
    )


@login_required
def shops_page(request):
    tenant_id = _current_tenant_id(request)
    if not tenant_id:
        raise Http404("Không xác định được tenant hiện tại")

    return render(
        request,
        "os_shops.html",
        {
            "current_tenant_id": tenant_id,
        },
    )


@login_required
def sku_page(request):
    tenant_id = _current_tenant_id(request)
    if not tenant_id:
        raise Http404("Không xác định được tenant hiện tại")

    return render(
        request,
        "os_sku.html",
        {
            "current_tenant_id": tenant_id,
        },
    )


@login_required
def contract_client_progress_page(request, contract_id: int, shop_id: int):
    return render(
        request,
        "os_contract_client_progress.html",
        {
            "current_tenant_id": _current_tenant_id(request),
            "contract_id": int(contract_id),
            "shop_id": int(shop_id),
        },
    )


@login_required
def contract_channel_content_page(request, contract_id: int):
    return render(
        request,
        "os_contract_channel_content.html",
        {
            "contract_id": int(contract_id),
            "current_tenant_id": _current_tenant_id(request),
        },
    )


@login_required
def founder_content_ai_dashboard_page(request):
    return render(
        request,
        "os_founder_content_ai_dashboard.html",
        {
            "current_tenant_id": _current_tenant_id(request),
        },
    )


@login_required
def founder_content_priority_dashboard_page(request):
    return render(
        request,
        "os_founder_content_priority_dashboard.html",
        {
            "current_tenant_id": _current_tenant_id(request),
        },
    )


@login_required
def content_work_sync_page(request):
    return render(
        request,
        "os_content_work_sync.html",
        {
            "current_tenant_id": _current_tenant_id(request),
            "contract_id": request.GET.get("contract_id") or "",
        },
    )