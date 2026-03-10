# apps/api/v1/contracts.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils.dateparse import parse_date
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.companies.models import Company
from apps.contracts.models import Contract, ContractShop
from apps.shops.models import Shop


def _tenant_id_from_request(request):
    # 1) Ưu tiên header từ page hiện tại
    tid = request.headers.get("X-Tenant-Id")
    if tid:
        try:
            return int(tid)
        except Exception:
            pass

    # 2) Ưu tiên membership thật của user
    try:
        from apps.accounts.models import Membership

        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            m = (
                Membership.objects.filter(user=user, is_active=True)
                .order_by("id")
                .first()
            )
            if m and m.tenant_id:
                return int(m.tenant_id)
    except Exception:
        pass

    # 3) Fallback request.tenant
    tenant = getattr(request, "tenant", None)
    tid = getattr(tenant, "id", None) if tenant else None
    if tid:
        try:
            return int(tid)
        except Exception:
            pass

    # 4) Fallback request.tenant_id
    tid = getattr(request, "tenant_id", None)
    if tid:
        try:
            return int(tid)
        except Exception:
            pass

    return None


def _company_qs():
    return getattr(Company, "objects_all", Company.objects)


def _shop_qs():
    return getattr(Shop, "objects_all", Shop.objects)


def _int_or_none(v):
    try:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        return int(s)
    except Exception:
        return None


def _dec(v, default: str = "0") -> Decimal:
    try:
        if v in (None, ""):
            return Decimal(default)
        return Decimal(str(v))
    except Exception:
        return Decimal(default)


def _clean_date(v):
    if not v:
        return None
    try:
        return parse_date(str(v))
    except Exception:
        return None


def _normalize_contract_kind(kind: str) -> str:
    s = str(kind or "").strip().lower()
    allowed = {
        "booking_freecast",
        "booking_percent",
        "channel_build",
        "operation",
        "job_small",
    }
    return s if s in allowed else ""


def _contract_type_from_kind(kind: str) -> str:
    if kind in ("booking_freecast", "booking_percent"):
        return Contract.Type.BOOKING
    if kind == "channel_build":
        return Contract.Type.CHANNEL
    return Contract.Type.OPERATION


def _money_str(v) -> str:
    try:
        return str(v or 0)
    except Exception:
        return "0"


def _resolve_contract_kind(x: Contract) -> str:
    meta = x.meta or {}
    return str(meta.get("contract_kind") or "").strip().lower()


def _serialize_contract(x: Contract) -> Dict[str, Any]:
    shops = []
    try:
        for cs in x.contract_shops.select_related("shop").all():
            shops.append(
                {
                    "id": cs.shop_id,
                    "name": getattr(cs.shop, "name", "") if getattr(cs, "shop", None) else "",
                }
            )
    except Exception:
        pass

    meta = x.meta or {}
    contract_kind = _resolve_contract_kind(x)

    return {
        "id": x.id,
        "tenant_id": x.tenant_id,
        "company_id": x.company_id,
        "code": x.code,
        "name": x.name,
        "contract_type": x.contract_type,
        "status": x.status,
        "partner_name": x.partner_name or "",
        "signed_at": x.signed_at.isoformat() if x.signed_at else None,
        "start_date": x.start_date.isoformat() if x.start_date else None,
        "end_date": x.end_date.isoformat() if x.end_date else None,
        "total_value": _money_str(x.total_value),
        "vat_percent": _money_str(x.vat_percent),
        "note": x.note or "",
        "meta": meta,
        "contract_kind": contract_kind,
        "shops": shops,
        "created_at": x.created_at.isoformat() if x.created_at else None,
        "updated_at": x.updated_at.isoformat() if x.updated_at else None,
    }


def _build_contract_meta(data) -> Dict[str, Any]:
    """
    Chuẩn business rule:
    - booking / xây kênh / hợp đồng lẻ: giá trị chưa VAT
    - vận hành:
        + fixed_fee_ex_vat: chưa VAT
        + net_revenue_percent_inc_vat: đã VAT
        + bậc doanh thu:
            <= mốc 1 => rate 1
            <= mốc 2 => rate 2
            >  mốc 2 => rate 3
    """

    # hỗ trợ cả tên field cũ lẫn tên field từ HTML hiện tại
    tier1_revenue_cap = _dec(
        data.get("tier1_revenue_cap")
        or data.get("revenue_tier_1")
    )
    tier2_revenue_cap = _dec(
        data.get("tier2_revenue_cap")
        or data.get("revenue_tier_2")
    )
    tier1_percent_inc_vat = _dec(
        data.get("tier1_percent_inc_vat")
        or data.get("revenue_tier_1_percent")
    )
    tier2_percent_inc_vat = _dec(
        data.get("tier2_percent_inc_vat")
        or data.get("revenue_tier_2_percent")
    )
    tier3_percent_inc_vat = _dec(
        data.get("tier3_percent_inc_vat")
        or data.get("revenue_tier_3_percent")
    )

    return {
        "contract_kind": _normalize_contract_kind(data.get("contract_kind") or ""),

        # BOOKING
        "booking_mode": str(data.get("booking_mode") or "").strip(),
        "koc_unit_price_ex_vat": _money_str(_dec(data.get("koc_unit_price_ex_vat"))),
        "booking_percent_ex_vat": _money_str(_dec(data.get("booking_percent_ex_vat"))),
        "estimated_koc_count": _int_or_none(data.get("estimated_koc_count")) or 0,
        "booking_note": str(data.get("booking_note") or "").strip(),

        # CHANNEL
        "channel_mode": str(data.get("channel_mode") or "").strip(),
        "channel_kpi_views": _money_str(_dec(data.get("channel_kpi_views"))),
        "channel_kpi_effective_rate": _money_str(_dec(data.get("channel_kpi_effective_rate"))),
        "channel_daily_tracking_enabled": True,
        "channel_extra_equipment_cost_ex_vat": _money_str(_dec(data.get("channel_extra_equipment_cost_ex_vat"))),
        "channel_extra_context_cost_ex_vat": _money_str(_dec(data.get("channel_extra_context_cost_ex_vat"))),
        "channel_extra_actor_cost_ex_vat": _money_str(_dec(data.get("channel_extra_actor_cost_ex_vat"))),
        "channel_note": str(data.get("channel_note") or "").strip(),

        # OPERATION
        "fixed_fee_ex_vat": _money_str(_dec(data.get("fixed_fee_ex_vat"))),
        "net_revenue_percent_inc_vat": _money_str(_dec(data.get("net_revenue_percent_inc_vat"))),
        "net_revenue_formula": "gmv - refund_cancel",
        "tier1_revenue_cap": _money_str(tier1_revenue_cap),
        "tier2_revenue_cap": _money_str(tier2_revenue_cap),
        "tier1_percent_inc_vat": _money_str(tier1_percent_inc_vat),
        "tier2_percent_inc_vat": _money_str(tier2_percent_inc_vat),
        "tier3_percent_inc_vat": _money_str(tier3_percent_inc_vat),
        "operation_note": str(data.get("operation_note") or "").strip(),

        # JOB SMALL / HỢP ĐỒNG LẺ
        "job_result_based_ex_vat": _money_str(_dec(data.get("job_result_based_ex_vat"))),
        "job_note": str(data.get("job_note") or "").strip(),
        "job_label": "Hợp đồng lẻ",
    }


class ContractListApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        company_id = _int_or_none(request.GET.get("company_id"))
        shop_id = _int_or_none(request.GET.get("shop_id"))
        keyword = (request.GET.get("q") or "").strip()
        status = (request.GET.get("status") or "").strip().lower()
        contract_kind = _normalize_contract_kind(request.GET.get("contract_kind") or "")

        qs = Contract.objects_all.filter(tenant_id=tenant_id).order_by("-id")

        if company_id:
            qs = qs.filter(company_id=company_id)

        if shop_id:
            qs = qs.filter(contract_shops__shop_id=shop_id).distinct()

        if status:
            qs = qs.filter(status=status)

        if contract_kind:
            qs = qs.filter(meta__contract_kind=contract_kind)

        if keyword:
            qs = qs.filter(
                Q(code__icontains=keyword)
                | Q(name__icontains=keyword)
                | Q(partner_name__icontains=keyword)
            )

        items = [
            _serialize_contract(x)
            for x in qs.prefetch_related("contract_shops__shop")[:100]
        ]

        return Response(
            {
                "ok": True,
                "tenant_id": tenant_id,
                "count": len(items),
                "items": items,
            }
        )


class ContractDetailApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, contract_id: int):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        obj = (
            Contract.objects_all
            .filter(id=int(contract_id), tenant_id=int(tenant_id))
            .prefetch_related("contract_shops__shop")
            .first()
        )
        if not obj:
            return Response({"ok": False, "message": "Không tìm thấy hợp đồng"}, status=404)

        return Response(
            {
                "ok": True,
                "tenant_id": tenant_id,
                "item": _serialize_contract(obj),
            }
        )


class ContractCreateApi(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        data = request.data or {}

        code = str(data.get("code") or "").strip()
        name = str(data.get("name") or "").strip()
        company_id = _int_or_none(data.get("company_id"))
        shop_id = _int_or_none(data.get("shop_id"))

        if not code:
            return Response({"ok": False, "message": "Thiếu mã hợp đồng"}, status=400)

        if not name:
            return Response({"ok": False, "message": "Thiếu tên hợp đồng"}, status=400)

        contract_kind = _normalize_contract_kind(data.get("contract_kind") or "")
        if not contract_kind:
            return Response({"ok": False, "message": "Loại hợp đồng không hợp lệ"}, status=400)

        contract_type = _contract_type_from_kind(contract_kind)

        total_value = _dec(data.get("total_value"))
        vat_percent = _dec(data.get("vat_percent"))

        company = None
        if company_id:
            company = _company_qs().filter(id=company_id, tenant_id=tenant_id).first()
            if not company:
                return Response(
                    {"ok": False, "message": "Company không thuộc tenant hiện tại"},
                    status=400,
                )

        shop = None
        if shop_id:
            shop = _shop_qs().filter(id=shop_id, tenant_id=tenant_id).first()
            if not shop:
                return Response(
                    {"ok": False, "message": "Shop không thuộc tenant hiện tại"},
                    status=400,
                )

        exists = Contract.objects_all.filter(tenant_id=tenant_id, code=code).exists()
        if exists:
            return Response(
                {"ok": False, "message": "Mã hợp đồng đã tồn tại trong tenant này"},
                status=400,
            )

        meta = _build_contract_meta(data)

        try:
            with transaction.atomic():
                obj = Contract.objects_all.create(
                    tenant_id=tenant_id,
                    company_id=company.id if company else None,
                    code=code,
                    name=name,
                    contract_type=contract_type,
                    status=Contract.Status.DRAFT,
                    partner_name=str(data.get("partner_name") or "").strip(),
                    signed_at=_clean_date(data.get("signed_at")),
                    start_date=_clean_date(data.get("start_date")),
                    end_date=_clean_date(data.get("end_date")),
                    total_value=total_value,
                    vat_percent=vat_percent,
                    note=str(data.get("note") or "").strip(),
                    meta=meta,
                )

                if shop:
                    ContractShop.objects_all.get_or_create(
                        tenant_id=tenant_id,
                        contract=obj,
                        shop=shop,
                    )

        except IntegrityError:
            return Response(
                {"ok": False, "message": "Không tạo được hợp đồng. Kiểm tra lại mã hợp đồng hoặc dữ liệu liên kết."},
                status=400,
            )
        except Exception as e:
            return Response(
                {"ok": False, "message": str(e)},
                status=400,
            )

        fresh = (
            Contract.objects_all
            .filter(tenant_id=tenant_id, id=obj.id)
            .prefetch_related("contract_shops__shop")
            .first()
        )

        return Response(
            {
                "ok": True,
                "tenant_id": tenant_id,
                "item": _serialize_contract(fresh),
            },
            status=201,
        )