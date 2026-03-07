from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.shops.models import Shop, ShopMember

# ✅ CHỐT KEY ĐỒNG BỘ (TenantResolveMiddleware cũng dùng tenant_id)
SESSION_TENANT_ID = "tenant_id"
SESSION_SHOP_ID = "active_shop_id"


def _get_req_tenant_id(request: HttpRequest) -> int | None:
    """
    tenant_id lấy theo thứ tự:
    1) request.tenant_id (do TenantResolveMiddleware set)
    2) request.tenant.id
    """
    tid = getattr(request, "tenant_id", None)
    if tid:
        try:
            return int(tid)
        except Exception:
            return None

    tenant = getattr(request, "tenant", None)
    if tenant and getattr(tenant, "id", None):
        try:
            return int(tenant.id)
        except Exception:
            return None

    return None


def _user_allowed_shop(user, shop_id: int) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    return ShopMember._base_manager.filter(user=user, shop_id=shop_id).exists()


@login_required
def app_home(request: HttpRequest) -> HttpResponse:
    """
    Nếu đã chọn shop -> vào dashboard
    Nếu chưa -> về select
    """
    if request.session.get(SESSION_SHOP_ID):
        return redirect("/dashboard/")
    return redirect("/app/select/")


@login_required
def select_workspace(request: HttpRequest) -> HttpResponse:
    tid = _get_req_tenant_id(request)

    # ✅ _base_manager: tránh scoped manager làm rỗng
    qs = Shop._base_manager.all()
    if tid:
        qs = qs.filter(tenant_id=tid)

    user = request.user
    if not (user.is_staff or user.is_superuser):
        member_shop_ids = ShopMember._base_manager.filter(user=user).values_list("shop_id", flat=True)
        qs = qs.filter(id__in=member_shop_ids)

    shops = list(qs.order_by("-id")[:200])

    # ✅ UX: nếu chỉ có 1 shop thì auto switch luôn
    if len(shops) == 1:
        shop = shops[0]
        request.session[SESSION_SHOP_ID] = shop.id
        request.session[SESSION_TENANT_ID] = getattr(shop, "tenant_id", None)
        request.session.modified = True
        return redirect("/dashboard/")

    return render(request, "dashboard/select_workspace.html", {"shops": shops})


@login_required
@require_POST
def switch_workspace(request: HttpRequest) -> HttpResponse:
    shop_id_raw = (request.POST.get("shop_id") or "").strip()
    if not shop_id_raw.isdigit():
        return redirect("/app/select/")

    shop_id = int(shop_id_raw)

    # ✅ bảo vệ tenant: chỉ cho switch trong tenant hiện tại
    tid = _get_req_tenant_id(request)
    shop_qs = Shop._base_manager.filter(id=shop_id)
    if tid:
        shop_qs = shop_qs.filter(tenant_id=tid)

    shop = shop_qs.first()
    if not shop:
        return redirect("/app/select/")

    # ✅ quyền: staff/superuser bypass; còn lại phải là ShopMember
    if not _user_allowed_shop(request.user, shop.id):
        return redirect("/app/select/")

    request.session[SESSION_SHOP_ID] = shop.id
    request.session[SESSION_TENANT_ID] = getattr(shop, "tenant_id", None)
    request.session.modified = True

    return redirect("/dashboard/")