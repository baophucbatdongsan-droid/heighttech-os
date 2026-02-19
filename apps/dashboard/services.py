# apps/dashboard/services.py
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from django.db.models import Sum
from django.utils import timezone

from apps.clients.models import Client
from apps.companies.models import Company
from apps.core.permissions import (
    resolve_user_role,
    get_user_company_ids,
    get_user_company_ids_from_shops,
    get_user_shop_ids,
    ROLE_FOUNDER,
    ROLE_HEAD,
    ROLE_ACCOUNT,
    ROLE_SALE,
    ROLE_OPERATOR,
    ROLE_CLIENT,
)


def _d(x) -> Decimal:
    try:
        return Decimal(str(x or "0"))
    except Exception:
        return Decimal("0")


def _has_field(model, field_name: str) -> bool:
    try:
        return any(f.name == field_name for f in model._meta.get_fields())
    except Exception:
        return False


def _sum_safe(qs, field: str) -> Decimal:
    if not _has_field(qs.model, field):
        return Decimal("0")
    return qs.aggregate(total=Sum(field))["total"] or Decimal("0")


def _filter_perf_by_company_ids(qs, company_ids: List[int]):
    Model = qs.model
    if _has_field(Model, "shop"):
        return qs.filter(shop__brand__company_id__in=company_ids)
    if _has_field(Model, "company"):
        return qs.filter(company_id__in=company_ids)
    return qs.none()


def _values_company_name_key(model) -> Optional[str]:
    if _has_field(model, "shop"):
        return "shop__brand__company__name"
    if _has_field(model, "company"):
        return "company__name"
    return None


class DashboardService:
    @staticmethod
    def build_context(request) -> Dict[str, Any]:
        from apps.performance.models import MonthlyPerformance  # local import tránh circular

        user = request.user
        role = resolve_user_role(user)

        # base query
        perf_qs = MonthlyPerformance.objects.all()
        if _has_field(MonthlyPerformance, "shop"):
            perf_qs = perf_qs.select_related("shop", "shop__brand", "shop__brand__company")
        elif _has_field(MonthlyPerformance, "company"):
            perf_qs = perf_qs.select_related("company")

        clients_qs = Client.objects.all()

        # =========================
        # SCOPE theo role
        # =========================
        selected_company_id: Optional[int] = None
        company_filter = (request.GET.get("company") or "").strip()

        if role == ROLE_FOUNDER:
            # founder xem all, optional filter theo company
            if company_filter:
                try:
                    selected_company_id = int(company_filter)
                    clients_qs = clients_qs.filter(company_id=selected_company_id)
                    perf_qs = _filter_perf_by_company_ids(perf_qs, [selected_company_id])
                except Exception:
                    selected_company_id = None

        elif role in (ROLE_HEAD, ROLE_ACCOUNT, ROLE_SALE, ROLE_OPERATOR):
            # các role nội bộ scope theo membership company_ids
            company_ids = get_user_company_ids(user)
            clients_qs = clients_qs.filter(company_id__in=company_ids)
            perf_qs = _filter_perf_by_company_ids(perf_qs, company_ids)

        elif role == ROLE_CLIENT:
            # portal scope theo shop_ids (nếu MonthlyPerformance có shop)
            shop_ids = get_user_shop_ids(user)
            if _has_field(MonthlyPerformance, "shop"):
                perf_qs = perf_qs.filter(shop_id__in=shop_ids)
            else:
                # schema không có shop -> map theo company ids suy ra từ shops
                company_ids = get_user_company_ids_from_shops(user)
                perf_qs = _filter_perf_by_company_ids(perf_qs, company_ids)

            # client vẫn cần clients_qs để KPI (nếu bạn muốn)
            company_ids = get_user_company_ids_from_shops(user)
            clients_qs = clients_qs.filter(company_id__in=company_ids)

        else:
            clients_qs = Client.objects.none()
            perf_qs = MonthlyPerformance.objects.none()

        # =========================
        # KPI
        # =========================
        total_clients = clients_qs.count()

        total_revenue = _sum_safe(perf_qs, "revenue")
        total_profit = _sum_safe(perf_qs, "profit")
        total_net = _sum_safe(perf_qs, "company_net_profit")

        # margin ưu tiên net, fallback profit
        base = total_net if total_net != 0 else total_profit
        margin = (base / total_revenue * Decimal("100")) if total_revenue > 0 else Decimal("0")

        # =========================
        # Chart theo tháng (nếu có đủ field)
        # =========================
        months: List[str] = []
        revenues: List[float] = []
        profits: List[float] = []
        margins: List[float] = []

        if _has_field(MonthlyPerformance, "month") and _has_field(MonthlyPerformance, "revenue") and _has_field(MonthlyPerformance, "profit"):
            monthly = (
                perf_qs.values("month")
                .annotate(revenue=Sum("revenue"), profit=Sum("profit"))
                .order_by("month")
            )
            for row in monthly:
                rev = _d(row.get("revenue"))
                prof = _d(row.get("profit"))
                months.append(row["month"].strftime("%m/%Y"))
                revenues.append(float(rev))
                profits.append(float(prof))
                margins.append(float((prof / rev) * 100) if rev > 0 else 0.0)

        # growth + forecast
        growth = 0.0
        if len(revenues) >= 2 and revenues[-2] > 0:
            growth = round(((revenues[-1] - revenues[-2]) / revenues[-2]) * 100, 2)

        forecast = 0.0
        if len(revenues) >= 2:
            forecast = revenues[-1] + (revenues[-1] - revenues[-2])
        elif len(revenues) == 1:
            forecast = revenues[0]

        # =========================
        # Expiring contracts (nếu Client có contract_end)
        # =========================
        expiring_clients = Client.objects.none()
        if hasattr(Client, "_meta") and any(f.name == "contract_end" for f in Client._meta.get_fields()):
            today = timezone.now().date()
            next_30 = today + timedelta(days=30)
            expiring_clients = clients_qs.filter(contract_end__range=(today, next_30))

        # =========================
        # Top / Loss companies
        # =========================
        key = _values_company_name_key(perf_qs.model)
        top_companies = []
        loss_companies = []

        if key and _has_field(MonthlyPerformance, "revenue"):
            top_companies = (
                perf_qs.values(key)
                .annotate(total_revenue=Sum("revenue"))
                .order_by("-total_revenue")[:5]
            )

        if key and _has_field(MonthlyPerformance, "company_net_profit"):
            loss_companies = (
                perf_qs.values(key)
                .annotate(total_net=Sum("company_net_profit"))
                .filter(total_net__lt=0)
                .order_by("total_net")[:20]
            )

        # =========================
        # Template chọn theo role
        # =========================
        template = "dashboard/dashboard.html"
        if role == ROLE_CLIENT:
            template = "dashboard/client_dashboard.html"  # file này bạn chưa có -> ở dưới mình đưa luôn

        return {
            "template": template,
            "role": role,

            # filters
            "companies": Company.objects.all() if role == ROLE_FOUNDER else [],
            "selected_company": selected_company_id,

            # KPI
            "total_clients": total_clients,
            "total_revenue": total_revenue,
            "total_profit": total_profit,
            "total_net": total_net,
            "margin": float(margin.quantize(Decimal("0.01"))),
            "growth": growth,
            "forecast": round(forecast, 0),

            # chart
            "months": json.dumps(months),
            "revenues": json.dumps(revenues),
            "profits": json.dumps(profits),
            "margins": json.dumps(margins),

            # tables
            "top_companies": top_companies,
            "loss_companies": loss_companies,
            "expiring_clients": expiring_clients,
        }