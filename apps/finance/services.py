# apps/finance/services.py (FULL FINAL)
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone


# =====================================================
# CONSTANTS
# =====================================================

# GMV fee after tax (VAT+TNDN gộp 30% -> còn 70%)
GMV_AFTER_TAX_RATE = Decimal("0.70")


# =====================================================
# HELPERS
# =====================================================

def d(value) -> Decimal:
    return Decimal(str(value or "0"))


def q2(value: Decimal) -> Decimal:
    return d(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _has_field(model, name: str) -> bool:
    try:
        return any(f.name == name for f in model._meta.get_fields())
    except Exception:
        return False


def _norm_industry_code(v: str) -> str:
    return (v or "").strip().lower()


def _norm_rule_version(v: str) -> str:
    return (v or "").strip()


# =====================================================
# COMMISSION ENGINE (RULE-DRIVEN)
# =====================================================

@dataclass
class CommissionSummary:
    # kept for backward compatibility
    gmv_rate: Decimal                 # rate (0.04 / 0.035 / 0.03 ...)
    gmv_fee_gross: Decimal            # amount
    gmv_fee_after_tax: Decimal        # amount (70%)

    team_bonus_percent: Decimal       # percent (20/25/30...)
    team_bonus_amount: Decimal        # amount

    fixed_fee_net: Decimal            # amount
    fixed_fee_net_after_tax: Decimal  # amount (70%)

    sale_commission: Decimal          # amount

    company_net_profit: Decimal       # amount


class CommissionEngine:
    """
    BACKWARD-COMPAT wrapper nhưng rule lấy từ apps.rules (founder-controlled).

    Input:
    - gmv
    - fixed_fee
    - growth_percent
    - months_active
    - vat_percent (optional)        -> nếu không set sẽ dùng rule output vat_rate
    - sale_percent (optional)       -> nếu không set sẽ dùng rule output sale_percent
    - tenant/shop/industry/version  -> để resolve engine đúng tenant + shop
    """

    def __init__(
        self,
        gmv: Decimal,
        fixed_fee: Decimal,
        growth_percent: Decimal,
        months_active: int,
        vat_percent: Decimal = Decimal("0"),
        sale_percent: Decimal = Decimal("0"),
        *,
        tenant_id: Optional[int] = None,
        shop_id: Optional[int] = None,
        industry_code: str = "default",
        rule_version: str = "v1",
        request_id: str = "",
        as_of: Optional[date] = None,  # thường là perf.month
    ):
        self.gmv = d(gmv)
        self.fixed_fee = d(fixed_fee)
        self.growth_percent = d(growth_percent)
        self.months_active = int(months_active or 0)

        self.vat_percent = d(vat_percent)
        self.sale_percent = d(sale_percent)

        self.tenant_id = tenant_id
        self.shop_id = shop_id
        self.industry_code = _norm_industry_code(industry_code or "default")
        self.rule_version = _norm_rule_version(rule_version or "v1")
        self.request_id = request_id or ""
        self.as_of = as_of

    def summary(self) -> CommissionSummary:
        # local import tránh circular
        from apps.rules.resolver import get_engine
        from apps.rules.types import CommissionInput, EngineContext

        ctx = EngineContext(
            tenant_id=self.tenant_id,
            shop_id=self.shop_id,
            industry_code=self.industry_code or "default",
            rule_version=self.rule_version or "v1",
            request_id=self.request_id,
        )

        as_of = self.as_of or timezone.now().date()
        engine = get_engine(ctx, as_of=as_of)

        out = engine.commission_calculate(
            CommissionInput(
                revenue=self.gmv,
                growth_percent=self.growth_percent,
                months_active=self.months_active,
            )
        )

        # --------------------------
        # Map rule output -> legacy fields
        # --------------------------

        # out.gmv_fee_percent is percent like 4 / 3.5 / 3
        gmv_rate = d(out.gmv_fee_percent) / Decimal("100")
        gmv_fee_gross = d(out.gmv_fee_amount)
        gmv_fee_after_tax = d(out.gmv_net_after_tax)

        team_bonus_percent = d(out.team_percent)
        team_bonus_amount = d(out.team_bonus)

        # fixed fee: prefer input fixed_fee if provided >0, else use rule fixed_fee
        fixed_fee = self.fixed_fee if self.fixed_fee > 0 else d(out.fixed_fee)

        # vat: prefer input if provided >0 else use rule vat_rate (0.10 -> 10.0)
        if self.vat_percent > 0:
            vat_percent = self.vat_percent
        else:
            vat_percent = d(out.vat_rate) * Decimal("100")

        fixed_fee_net = fixed_fee * (Decimal("1") - (vat_percent / Decimal("100")))
        fixed_fee_net_after_tax = fixed_fee_net * GMV_AFTER_TAX_RATE

        # sale percent: prefer input if provided >0 else use rule sale_percent
        sale_percent = self.sale_percent if self.sale_percent > 0 else d(out.sale_percent)

        # IMPORTANT:
        # - Nếu bạn có input sale_percent -> tính sale_commission theo fixed_fee_net_after_tax
        # - Nếu không -> dùng rule output sale_bonus (rule đang tính theo fixed_net * sale_percent)
        if self.sale_percent > 0:
            sale_commission = fixed_fee_net_after_tax * (sale_percent / Decimal("100"))
        else:
            sale_commission = d(out.sale_bonus)

        company_net_profit = (
            gmv_fee_after_tax
            + fixed_fee_net_after_tax
            - team_bonus_amount
            - sale_commission
        )

        return CommissionSummary(
            gmv_rate=q2(gmv_rate),
            gmv_fee_gross=q2(gmv_fee_gross),
            gmv_fee_after_tax=q2(gmv_fee_after_tax),

            team_bonus_percent=q2(team_bonus_percent),
            team_bonus_amount=q2(team_bonus_amount),

            fixed_fee_net=q2(fixed_fee_net),
            fixed_fee_net_after_tax=q2(fixed_fee_net_after_tax),

            sale_commission=q2(sale_commission),

            company_net_profit=q2(company_net_profit),
        )


# =====================================================
# AGENCY FINANCE SERVICE (TENANT-SAFE + RULE SNAPSHOT)
# =====================================================

class AgencyFinanceService:
    """
    Enterprise layer:
    - Tổng hợp số liệu theo tháng vào AgencyMonthlyFinance (snapshot)
    - OPEN: được phép recalc/update
    - LOCKED/FINALIZED: freeze, không update
    - FINALIZE: chụp Rule Snapshot (industry/version/engine/effective/meta)

    Tenant-safe:
    - nếu AgencyMonthlyFinance có tenant field => snapshot theo (tenant, month)
    - nếu không có => giữ behavior cũ
    """

    @staticmethod
    def _get_or_create_snapshot(month, *, tenant_id: Optional[int] = None):
        from apps.finance.models import AgencyMonthlyFinance  # local import tránh circular

        lookup: Dict[str, Any] = {"month": month}
        if tenant_id and _has_field(AgencyMonthlyFinance, "tenant"):
            lookup["tenant_id"] = tenant_id

        obj, _ = AgencyMonthlyFinance.objects.get_or_create(**lookup)
        return obj

    @staticmethod
    def calculate_totals(month, *, tenant_id: Optional[int] = None) -> Dict[str, Decimal]:
        """
        Tổng hợp từ MonthlyPerformance.
        """
        from apps.performance.models import MonthlyPerformance

        qs = MonthlyPerformance.objects.filter(month=month)
        if tenant_id and _has_field(MonthlyPerformance, "tenant"):
            qs = qs.filter(tenant_id=tenant_id)

        total_gmv_fee = qs.aggregate(total=Sum("gmv_fee_after_tax"))["total"] or Decimal("0")
        total_fixed_fee_net = qs.aggregate(total=Sum("fixed_fee_net"))["total"] or Decimal("0")
        total_fixed_fee_net_after_tax = qs.aggregate(total=Sum("fixed_fee_net_after_tax"))["total"] or Decimal("0")

        total_sale = qs.aggregate(total=Sum("sale_commission"))["total"] or Decimal("0")
        total_team = qs.aggregate(total=Sum("bonus_amount"))["total"] or Decimal("0")

        operating_cost = Decimal("0")

        net = (
            d(total_gmv_fee)
            + d(total_fixed_fee_net_after_tax)
            - d(total_sale)
            - d(total_team)
            - d(operating_cost)
        )

        return {
            "total_gmv_fee_after_tax": q2(d(total_gmv_fee)),
            "total_fixed_fee_net": q2(d(total_fixed_fee_net)),
            "total_sale_commission": q2(d(total_sale)),
            "total_team_bonus": q2(d(total_team)),
            "total_operating_cost": q2(d(operating_cost)),
            "agency_net_profit": q2(net),
        }

    @staticmethod
    def _try_snapshot_rule(obj, *, tenant_id: Optional[int], as_of: date) -> None:
        """
        Best-effort rule snapshot.
        Only sets fields if they exist on AgencyMonthlyFinance.
        """
        # local import tránh circular
        from apps.rules.registry import list_rules
        from apps.rules.resolver import resolve_engine_cls

        # hiện tại chưa có config rule theo tenant/company -> snapshot default/v1
        industry_code = "default"
        rule_version = "v1"

        engine_cls = resolve_engine_cls(industry_code=industry_code, rule_version=rule_version, as_of=as_of)
        engine_name = getattr(engine_cls, "ENGINE_NAME", engine_cls.__name__)

        eff_date = None
        regs = [
            r for r in list_rules(industry_code=industry_code, rule_version=rule_version)
            if r.effective_date <= as_of
        ]
        if regs:
            regs.sort(key=lambda r: r.effective_date)
            eff_date = regs[-1].effective_date

        payload: Dict[str, Any] = {
            "industry_code": industry_code,
            "rule_version": rule_version,
            "engine_class": f"{engine_cls.__module__}.{engine_cls.__name__}",
            "engine_name": engine_name,
            "as_of": str(as_of),
            "effective_date": str(eff_date) if eff_date else None,
            "tenant_id": tenant_id,
        }

        if hasattr(obj, "rule_industry_code"):
            obj.rule_industry_code = industry_code
        if hasattr(obj, "rule_version"):
            obj.rule_version = rule_version
        if hasattr(obj, "rule_engine_name"):
            obj.rule_engine_name = engine_name
        if hasattr(obj, "rule_effective_date"):
            obj.rule_effective_date = eff_date
        if hasattr(obj, "rule_snapshot_json"):
            obj.rule_snapshot_json = payload

    @staticmethod
    @transaction.atomic
    def calculate_or_update(month, *, tenant_id: Optional[int] = None):
        obj = AgencyFinanceService._get_or_create_snapshot(month, tenant_id=tenant_id)

        # nếu model có can_edit -> respect; không có thì coi như editable
        if hasattr(obj, "can_edit") and not obj.can_edit():
            return obj

        totals = AgencyFinanceService.calculate_totals(month, tenant_id=tenant_id)
        for k, v in totals.items():
            setattr(obj, k, v)

        if hasattr(obj, "calculated_at"):
            obj.calculated_at = timezone.now()

        update_fields = []
        for f in [
            "total_gmv_fee_after_tax",
            "total_fixed_fee_net",
            "total_sale_commission",
            "total_team_bonus",
            "total_operating_cost",
            "agency_net_profit",
            "calculated_at",
            "updated_at",
        ]:
            if hasattr(obj, f):
                update_fields.append(f)

        obj.save(update_fields=update_fields)
        return obj

    @staticmethod
    @transaction.atomic
    def lock_month(month, *, tenant_id: Optional[int] = None):
        obj = AgencyFinanceService.calculate_or_update(month, tenant_id=tenant_id)
        if hasattr(obj, "lock"):
            obj.lock()
        return obj

    @staticmethod
    @transaction.atomic
    def finalize_month(month, *, tenant_id: Optional[int] = None):
        """
        FINALIZE:
        - Recalc (nếu còn OPEN)
        - Snapshot rule
        - finalize() => freeze
        """
        obj = AgencyFinanceService._get_or_create_snapshot(month, tenant_id=tenant_id)

        if hasattr(obj, "can_edit") and obj.can_edit():
            obj = AgencyFinanceService.calculate_or_update(month, tenant_id=tenant_id)

        as_of = month if isinstance(month, date) else timezone.now().date()
        AgencyFinanceService._try_snapshot_rule(obj, tenant_id=tenant_id, as_of=as_of)

        snap_fields = [
            f for f in
            ["rule_industry_code", "rule_version", "rule_engine_name", "rule_effective_date", "rule_snapshot_json", "updated_at"]
            if hasattr(obj, f)
        ]
        if snap_fields:
            obj.save(update_fields=snap_fields)

        if hasattr(obj, "finalize"):
            obj.finalize()
        return obj

    @staticmethod
    @transaction.atomic
    def reopen_month(month, *, tenant_id: Optional[int] = None):
        """
        REOPEN:
        - Nếu model có reopen(): dùng luôn (và nó sẽ chặn FINALIZED theo policy bạn set)
        - Nếu không có: fallback set status OPEN (nhưng vẫn nên tránh reopen finalized)
        """
        from apps.finance.models import AgencyMonthlyFinance

        obj = AgencyFinanceService._get_or_create_snapshot(month, tenant_id=tenant_id)

        if hasattr(obj, "reopen") and callable(getattr(obj, "reopen")):
            obj.reopen()
            return obj

        # fallback (older model)
        if hasattr(obj, "status") and getattr(obj, "status", None) == getattr(AgencyMonthlyFinance, "STATUS_FINALIZED", "finalized"):
            raise ValueError(f"Month {month} is FINALIZED. Reopen is not allowed.")

        if hasattr(AgencyMonthlyFinance, "STATUS_OPEN") and hasattr(obj, "status"):
            obj.status = AgencyMonthlyFinance.STATUS_OPEN
        if hasattr(obj, "locked_at"):
            obj.locked_at = None
        if hasattr(obj, "finalized_at"):
            obj.finalized_at = None

        update_fields = [f for f in ["status", "locked_at", "finalized_at", "updated_at"] if hasattr(obj, f)]
        obj.save(update_fields=update_fields)
        return obj