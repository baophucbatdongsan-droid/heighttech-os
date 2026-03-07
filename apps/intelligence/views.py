from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render

from apps.shops.models import Shop
from apps.intelligence.services import FounderIntelligenceService


def _require_founder(request) -> None:
    user = getattr(request, "user", None)
    role = str(getattr(request, "role", "") or "").lower()

    # ✅ founder/admin/staff/superuser mới vào
    if not user or not user.is_authenticated:
        raise PermissionDenied("Bạn chưa đăng nhập.")
    if not (user.is_staff or user.is_superuser or role in {"founder", "admin"}):
        raise PermissionDenied("Bạn không có quyền truy cập trang này.")


@login_required
def founder_dashboard(request):
    _require_founder(request)

    month = request.GET.get("month")  # "YYYY-MM-01"
    # (tuỳ service của anh) nếu cần tenant:
    tenant_id = getattr(request, "tenant_id", None)

    context = FounderIntelligenceService.build_founder_context(
        month=month,
        tenant_id=tenant_id,  # nếu service support; không support thì bỏ param này
    )
    return render(request, "intelligence/founder_dashboard.html", context)


@login_required
def founder_shop_detail(request, shop_id: int):
    _require_founder(request)

    shop = get_object_or_404(Shop, pk=shop_id)
    month = request.GET.get("month")
    tenant_id = getattr(request, "tenant_id", None)

    context = FounderIntelligenceService.build_shop_deep_context(
        shop=shop,
        month=month,
        tenant_id=tenant_id,  # nếu service support; không support thì bỏ
    )
    return render(request, "intelligence/founder_shop_detail.html", context)