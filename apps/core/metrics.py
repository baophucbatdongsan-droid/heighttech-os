from __future__ import annotations

from django.db.models import Count
from django.utils import timezone

from apps.companies.models import Company
from apps.brands.models import Brand
from apps.shops.models import Shop
from apps.performance.models import MonthlyPerformance


def compute_system_metrics():
    today = timezone.now().date()

    return {
        "date": today.isoformat(),
        "companies": Company.objects.count(),
        "brands": Brand.objects.count(),
        "shops": Shop.objects.count(),
        "performances": MonthlyPerformance.objects.count(),
        "active_shops": Shop.objects.filter(is_active=True).count(),
    }