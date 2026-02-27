from django.db.models import Sum
from apps.performance.models import MonthlyPerformance


def get_loss_alerts(queryset):
    alerts = []

    companies = queryset.values("company").distinct()

    for company in companies:
        records = (
            queryset
            .filter(company_id=company["company"])
            .order_by("-month")[:2]
        )

        if len(records) == 2:
            if records[0].profit < 0 and records[1].profit < 0:
                alerts.append({
                    "type": "loss_2_months",
                    "company": records[0].company.name
                })

    return alerts


def get_margin_alerts(queryset):
    alerts = []

    companies = queryset.values("company").distinct()

    for company in companies:
        latest = (
            queryset
            .filter(company_id=company["company"])
            .order_by("-month")
            .first()
        )

        if latest and latest.revenue > 0:
            margin = (latest.profit / latest.revenue) * 100
            if margin < 10:
                alerts.append({
                    "type": "low_margin",
                    "company": latest.company.name,
                    "margin": round(margin, 2)
                })

    return alerts


def get_growth_alerts(queryset):
    alerts = []

    companies = queryset.values("company").distinct()

    for company in companies:
        records = (
            queryset
            .filter(company_id=company["company"])
            .order_by("-month")[:2]
        )

        if len(records) == 2:
            last = records[0]
            prev = records[1]

            if prev.revenue > 0:
                growth = ((last.revenue - prev.revenue) / prev.revenue) * 100
                if growth < -20:
                    alerts.append({
                        "type": "profit_drop",
                        "company": last.company.name,
                        "growth": round(growth, 2)
                    })

    return alerts