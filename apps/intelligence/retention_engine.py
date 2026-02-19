from datetime import timedelta
from django.utils import timezone

from apps.intelligence.models import ShopRetentionState
from apps.performance.models import MonthlyPerformance


class RetentionEngine:

    @staticmethod
    def calculate(month):

        rows = MonthlyPerformance.objects.filter(month=month)

        for perf in rows:
            score = 0

            # Growth
            if perf.growth_percent > 0:
                score += 20

            # Margin
            if perf.company_net_profit > 0:
                score += 20

            # No loss
            if perf.profit > 0:
                score += 20

            # Simple risk mapping
            if perf.growth_percent < 0:
                score -= 10

            score = max(0, min(100, score))

            escalation = 0
            badge = "STABLE"

            if score < 40:
                escalation = 2
                badge = "AT_RISK"
            elif score < 60:
                escalation = 1
                badge = "WATCHLIST"
            elif score > 80:
                badge = "TOP_GROWTH"

            ShopRetentionState.objects.update_or_create(
                month=month,
                shop_id=perf.shop_id,
                defaults={
                    "shop_name": perf.shop.name,
                    "company_name": perf.shop.brand.company.name,
                    "retention_score": score,
                    "escalation_level": escalation,
                    "badge": badge,
                    "auto_flag": escalation >= 2,
                }
            )