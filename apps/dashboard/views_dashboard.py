from __future__ import annotations

from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import redirect, render

from apps.performance.models import MonthlyPerformance
from apps.shops.models import Shop

SESSION_CURRENT_SHOP = "current_shop_id"


@login_required
def dashboard_home(request):
    shop_id = request.session.get(SESSION_CURRENT_SHOP)
    if not shop_id:
        return redirect("/app/select/")

    shop = Shop.objects.filter(id=shop_id).first()
    if not shop:
        request.session.pop(SESSION_CURRENT_SHOP, None)
        return redirect("/app/select/")

    qs = MonthlyPerformance.objects.filter(shop_id=shop_id).order_by("month")

    total_revenue = qs.aggregate(v=Sum("revenue"))["v"] or Decimal("0")
    total_profit = qs.aggregate(v=Sum("profit"))["v"] or Decimal("0")
    total_net = qs.aggregate(v=Sum("company_net_profit"))["v"] or Decimal("0")

    margin = Decimal("0")
    if total_revenue > 0:
        margin = (total_net / total_revenue) * Decimal("100")

    months = [p.month.strftime("%Y-%m") for p in qs]
    revenues = [float(p.revenue) for p in qs]
    profits = [float(p.profit) for p in qs]

    ctx = {
        "role": getattr(request, "role", "operator"),
        "shop": shop,

        "total_clients": 1,  # tạm: hiện coi 1 workspace = 1 shop
        "total_revenue": total_revenue,
        "total_profit": total_profit,
        "total_net": total_net,
        "margin": float(margin.quantize(Decimal("0.01"))),

        "months": months,
        "revenues": revenues,
        "profits": profits,

        "top_companies": [],
        "loss_companies": [],
        "risk_loss": total_net < 0,
        "risk_growth": False,
        "anomalies": [],
    }
    return render(request, "dashboard/control_dashboard.html", ctx)