from decimal import Decimal
from django.db.models import Avg
from django.utils import timezone

from apps.performance.models import MonthlyPerformance


class ShopRiskEngine:

    def __init__(self, shop):
        self.shop = shop

    def evaluate(self):
        performances = MonthlyPerformance.objects.filter(
            shop=self.shop
        ).order_by("-month")[:3]

        if not performances:
            return

        latest = performances[0]

        risk_score = 0

        # 1️⃣ Margin thấp
        if latest.revenue > 0:
            margin = (latest.company_net_profit / latest.revenue) * 100
            if margin < 10:
                risk_score += 30

        # 2️⃣ 2 tháng giảm liên tục
        if len(performances) >= 3:
            if (
                performances[0].revenue < performances[1].revenue and
                performances[1].revenue < performances[2].revenue
            ):
                risk_score += 30

        # 3️⃣ Growth âm mạnh
        if latest.growth_percent < -20:
            risk_score += 40

        # 4️⃣ Sắp hết hợp đồng
        if self.shop.contract_end:
            days_left = (self.shop.contract_end - timezone.now().date()).days
            if 0 <= days_left <= 30:
                risk_score += 20

        # =========================

        self.shop.risk_score = risk_score

        if risk_score >= 70:
            self.shop.mark_risk()
        elif risk_score >= 30:
            self.shop.mark_warning()
        else:
            self.shop.mark_operating()