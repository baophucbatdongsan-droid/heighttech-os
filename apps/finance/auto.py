from datetime import date
from django.utils import timezone

from apps.finance.services import AgencyFinanceService


class AutoFinanceEngine:
    @staticmethod
    def auto_lock_previous_month():
        """
        Nếu đã qua ngày 5 của tháng mới → lock tháng trước
        """
        today = timezone.now().date()
        if today.day < 5:
            return

        first_day_this_month = date(today.year, today.month, 1)

        # lùi 1 tháng
        if first_day_this_month.month == 1:
            prev_month = date(first_day_this_month.year - 1, 12, 1)
        else:
            prev_month = date(first_day_this_month.year, first_day_this_month.month - 1, 1)

        AgencyFinanceService.lock_month(prev_month)