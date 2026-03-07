# apps/core/views_workspace.py
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.shops.models import Shop

SESSION_CURRENT_SHOP = "current_shop_id"


def _get_user_shops(user):
    # user là member shop nào -> thấy shop đó
    return Shop.objects.filter(members__user=user).distinct().order_by("name")


@login_required
def app_home(request):
    """
    Entry của /app/
    - Nếu đã có current_shop_id -> vào /dashboard/
    - Nếu chưa -> đi chọn workspace
    """
    if request.session.get(SESSION_CURRENT_SHOP):
        return redirect("/dashboard/")
    return redirect("/app/select/")


@login_required
def select_workspace(request):
    shops = _get_user_shops(request.user)

    if shops.count() == 1:
        request.session[SESSION_CURRENT_SHOP] = shops.first().id
        return redirect("/dashboard/")

    current_shop_id = request.session.get(SESSION_CURRENT_SHOP)
    return render(
        request,
        "core/select_workspace.html",
        {"shops": shops, "current_shop_id": current_shop_id},
    )


@login_required
@require_POST
def switch_workspace(request):
    shop_id = request.POST.get("shop_id")
    shops = _get_user_shops(request.user)

    try:
        shop_id = int(shop_id)
    except Exception:
        return redirect("/app/select/")

    if not shops.filter(id=shop_id).exists():
        return redirect("/app/select/")

    request.session[SESSION_CURRENT_SHOP] = shop_id
    return redirect("/dashboard/")