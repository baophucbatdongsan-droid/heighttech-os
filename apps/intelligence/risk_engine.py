from __future__ import annotations
from decimal import Decimal
from django.db.models import Avg
from django.utils import timezone

from apps.performance.models import MonthlyPerformance


from typing import Dict, Any, List


def detect_risks(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Phát hiện rủi ro hệ thống
    """

    risks: List[Dict[str, Any]] = []

    overdue = context.get("overdue_tasks", 0)

    if overdue >= 10:
        risks.append(
            {
                "ma": "TASK_QUA_HAN",
                "tieu_de": "Nhiều công việc bị quá hạn",
                "muc_do": "cao",
                "mo_ta": f"Có {overdue} công việc quá hạn",
                "goi_y": "Cần kiểm tra lại tiến độ xử lý",
            }
        )

    shops = context.get("shops_health", [])

    for shop in shops:
        score = shop.get("health_score", 100)

        if score < 50:
            risks.append(
                {
                    "ma": "SHOP_RUI_RO",
                    "tieu_de": "Shop có dấu hiệu rủi ro",
                    "muc_do": "trung_binh",
                    "mo_ta": f"Điểm sức khỏe shop thấp ({score})",
                    "goi_y": "Cần kiểm tra hoạt động của shop",
                    "shop_id": shop.get("shop_id"),
                }
            )

    return risks

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