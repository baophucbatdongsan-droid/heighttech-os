from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404

from apps.shops.models import Shop
from apps.intelligence.services import FounderIntelligenceService


@login_required
def founder_dashboard(request):
    month = request.GET.get("month")  # "YYYY-MM-01"
    context = FounderIntelligenceService.build_founder_context(month=month)
    return render(request, "intelligence/founder_dashboard.html", context)


@login_required
def founder_shop_detail(request, shop_id: int):
    shop = get_object_or_404(Shop, pk=shop_id)
    month = request.GET.get("month")
    context = FounderIntelligenceService.build_shop_deep_context(shop=shop, month=month)
    return render(request, "intelligence/founder_shop_detail.html", context)