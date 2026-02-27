# apps/dashboard/views.py
from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Sum
from django.shortcuts import render
from django.utils import timezone

from apps.clients.models import Client
from apps.companies.models import Company
from apps.performance.models import MonthlyPerformance

from apps.core.decorators import require_ability
from apps.core.policy import VIEW_DASHBOARD


# =====================================================
# SAFE PERMISSIONS IMPORT
# =====================================================
def _safe_import_permissions():
    try:
        from apps.core import permissions as p  # type: ignore
    except Exception:
        p = None

    def get(name):
        return getattr(p, name, None) if p else None

    return {
        "resolve_user_role": get("resolve_user_role"),
        "get_user_company_ids": get("get_user_company_ids"),
        "get_user_shop_ids": get("get_user_shop_ids"),
        "get_user_company_ids_from_shops": get("get_user_company_ids_from_shops"),
    }


P = _safe_import_permissions()


def _resolve_role(user) -> str:
    fn = P["resolve_user_role"]
    if callable(fn):
        try:
            return (fn(user) or "none").lower()
        except Exception:
            pass

    if getattr(user, "is_superuser", False):
        return "founder"
    return "none"


def _has_field(model, field_name: str) -> bool:
    try:
        return any(f.name == field_name for f in model._meta.get_fields())
    except Exception:
        return False


def _sum_safe(qs, field: str) -> Decimal:
    if not qs or not hasattr(qs, "model"):
        return Decimal("0")
    if not _has_field(qs.model, field):
        return Decimal("0")
    return qs.aggregate(total=Sum(field))["total"] or Decimal("0")


def _filter_perf_by_company_ids(qs, company_ids: List[int]):
    """
    Support 2 schema:
    - MonthlyPerformance có shop FK: shop__brand__company_id
    - MonthlyPerformance có company FK: company_id
    """
    if not company_ids:
        return qs.none()

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


def _get_shop_ids_for_user(user) -> List[int]:
    fn = P["get_user_shop_ids"]
    if callable(fn):
        try:
            return list(fn(user))
        except Exception:
            pass

    # fallback via ShopMember
    try:
        from apps.shops.models import ShopMember  # local import
        return list(
            ShopMember.objects.filter(user=user, is_active=True).values_list("shop_id", flat=True)
        )
    except Exception:
        return []


def _get_company_ids_for_user(user) -> List[int]:
    fn = P["get_user_company_ids"]
    if callable(fn):
        try:
            return list(fn(user))
        except Exception:
            pass

    # fallback via shops -> brand -> company
    try:
        from apps.shops.models import ShopMember  # local import
        return list(
            ShopMember.objects.filter(user=user, is_active=True)
            .values_list("shop__brand__company_id", flat=True)
            .distinct()
        )
    except Exception:
        return []


def _get_company_ids_from_shops(user) -> List[int]:
    fn = P["get_user_company_ids_from_shops"]
    if callable(fn):
        try:
            return list(fn(user))
        except Exception:
            pass
    return _get_company_ids_for_user(user)


def _client_has_contract_end() -> bool:
    try:
        return any(f.name == "contract_end" for f in Client._meta.get_fields())
    except Exception:
        return False


# =====================================================
# MAIN VIEW
# =====================================================
@login_required
@require_ability(VIEW_DASHBOARD)
def dashboard_view(request):
    user = request.user
    role = _resolve_role(user)

    # Founder có thể filter company
    company_filter = (request.GET.get("company") or "").strip()
    cache_key = f"dashboard_ctx:u{user.id}:{role}:c{company_filter}"

    cached = cache.get(cache_key)
    if cached:
        template = cached.pop("_template", "dashboard/dashboard.html")
        return render(request, template, cached)

    # base querysets
    clients = Client.objects.none()
    performances = MonthlyPerformance.objects.none()

    # ---------- FOUNDER / SUPERUSER ----------
    if getattr(user, "is_superuser", False) or role == "founder":
        role = "founder"
        clients = Client.objects.all()
        performances = MonthlyPerformance.objects.all()

    # ---------- HEAD ----------
    elif role == "head":
        company_ids = _get_company_ids_for_user(user)
        clients = Client.objects.filter(company_id__in=company_ids)
        performances = _filter_perf_by_company_ids(MonthlyPerformance.objects.all(), company_ids)

    # ---------- ACCOUNT ----------
    elif role == "account":
        clients = Client.objects.filter(account_manager=user)
        company_ids = list(clients.values_list("company_id", flat=True).distinct())
        performances = _filter_perf_by_company_ids(MonthlyPerformance.objects.all(), company_ids)

    # ---------- OPERATOR ----------
    elif role == "operator":
        clients = Client.objects.filter(operator=user)
        company_ids = list(clients.values_list("company_id", flat=True).distinct())
        performances = _filter_perf_by_company_ids(MonthlyPerformance.objects.all(), company_ids)

    # ---------- CLIENT (SHOP PORTAL) ----------
    elif role == "client":
        shop_ids = _get_shop_ids_for_user(user)

        if _has_field(MonthlyPerformance, "shop"):
            performances = MonthlyPerformance.objects.filter(shop_id__in=shop_ids)
        else:
            company_ids = _get_company_ids_from_shops(user)
            performances = _filter_perf_by_company_ids(MonthlyPerformance.objects.all(), company_ids)

        company_ids = _get_company_ids_from_shops(user)
        clients = Client.objects.filter(company_id__in=company_ids)

    else:
        role = "none"

    # =====================================================
    # FOUNDER FILTER BY COMPANY (optional)
    # =====================================================
    selected_company_id: Optional[int] = None
    if role == "founder" and company_filter:
        try:
            selected_company_id = int(company_filter)
            clients = clients.filter(company_id=selected_company_id)
            performances = _filter_perf_by_company_ids(performances, [selected_company_id])
        except (TypeError, ValueError):
            selected_company_id = None

    # =====================================================
    # KPI
    # =====================================================
    total_clients = clients.count()

    total_revenue = _sum_safe(performances, "revenue")
    total_profit = _sum_safe(performances, "profit")
    total_company_net_profit = _sum_safe(performances, "company_net_profit")
    total_net = total_company_net_profit if total_company_net_profit != 0 else total_profit

    margin = (total_net / total_revenue * Decimal("100")) if total_revenue > 0 else Decimal("0")

    # =====================================================
    # MONTHLY CHART
    # =====================================================
    months: List[str] = []
    revenues: List[float] = []
    profits: List[float] = []

    if (
        _has_field(MonthlyPerformance, "month")
        and _has_field(MonthlyPerformance, "revenue")
        and _has_field(MonthlyPerformance, "profit")
    ):
        monthly = (
            performances.values("month")
            .annotate(revenue=Sum("revenue"), profit=Sum("profit"))
            .order_by("month")
        )
        for row in monthly:
            m = row.get("month")
            rev = row.get("revenue") or Decimal("0")
            prof = row.get("profit") or Decimal("0")
            months.append(m.strftime("%m/%Y") if m else "")
            revenues.append(float(rev))
            profits.append(float(prof))

    # =====================================================
    # MoM Growth + Forecast
    # =====================================================
    growth = 0.0
    if len(revenues) >= 2 and revenues[-2] > 0:
        growth = round(((revenues[-1] - revenues[-2]) / revenues[-2]) * 100, 2)

    forecast = 0.0
    if len(revenues) >= 2:
        forecast = revenues[-1] + (revenues[-1] - revenues[-2])
    elif len(revenues) == 1:
        forecast = revenues[0]

    # =====================================================
    # EXPIRING CONTRACTS (safe)
    # =====================================================
    expiring_clients = Client.objects.none()
    if _client_has_contract_end():
        today = timezone.now().date()
        next_30 = today + timedelta(days=30)
        expiring_clients = clients.filter(contract_end__range=(today, next_30))

    # =====================================================
    # TOP / LOSS COMPANIES
    # =====================================================
    company_name_key = _values_company_name_key(performances.model)
    top_companies = []
    loss_companies = []

    if company_name_key and _has_field(MonthlyPerformance, "revenue"):
        top_companies = (
            performances.values(company_name_key)
            .annotate(total_revenue=Sum("revenue"))
            .order_by("-total_revenue")[:5]
        )

    metric = None
    if _has_field(MonthlyPerformance, "company_net_profit"):
        metric = "company_net_profit"
    elif _has_field(MonthlyPerformance, "profit"):
        metric = "profit"

    if company_name_key and metric:
        loss_companies = (
            performances.values(company_name_key)
            .annotate(total_metric=Sum(metric))
            .filter(total_metric__lt=0)
            .order_by("total_metric")[:20]
        )

    # =====================================================
    # ANOMALY (simple)
    # =====================================================
    anomalies: List[str] = []
    if revenues:
        avg_rev = sum(revenues) / len(revenues)
        if avg_rev > 0:
            for i, rev in enumerate(revenues):
                if abs(rev - avg_rev) / avg_rev > 0.4:
                    anomalies.append(months[i])

    try:
        risk_loss = loss_companies.exists()
    except Exception:
        risk_loss = bool(loss_companies)
    risk_growth = growth < 0

    # =====================================================
    # TEMPLATE SWITCH
    # =====================================================
    template = "dashboard/dashboard.html"
    if role == "client":
        template = "dashboard/client_dashboard.html"

    context: Dict[str, Any] = {
        "role": role,

        # filters (founder)
        "companies": Company.objects.all() if role == "founder" else [],
        "selected_company": selected_company_id,

        # KPI
        "total_clients": total_clients,
        "total_revenue": total_revenue,
        "total_profit": total_profit,
        "total_net": total_net,
        "margin": float(margin.quantize(Decimal("0.01"))),
        "growth": growth,
        "forecast": round(forecast, 0),

        # Chart.js
        "months": json.dumps(months),
        "revenues": json.dumps(revenues),
        "profits": json.dumps(profits),

        # Tables
        "top_companies": top_companies,
        "loss_companies": loss_companies,
        "expiring_clients": expiring_clients,

        # Alerts
        "anomalies": anomalies,
        "risk_loss": risk_loss,
        "risk_growth": risk_growth,
    }

    cache.set(cache_key, {**context, "_template": template}, timeout=60 * 5)
    return render(request, template, context)