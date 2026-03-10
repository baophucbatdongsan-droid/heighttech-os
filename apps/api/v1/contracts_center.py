from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.contracts.models import (
    Contract,
    ContractBookingItem,
    ContractMilestone,
    ContractPayment,
)
from apps.shops.models import Shop


def _tenant_id_from_request(request):
    tid = request.headers.get("X-Tenant-Id")
    if tid:
        try:
            return int(tid)
        except Exception:
            pass

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

    tenant = getattr(request, "tenant", None)
    tid = getattr(tenant, "id", None) if tenant else None
    if tid:
        try:
            return int(tid)
        except Exception:
            pass

    tid = getattr(request, "tenant_id", None)
    if tid:
        try:
            return int(tid)
        except Exception:
            pass

    return None


def _get_contract_or_none(contract_id: int, tenant_id: int):
    return (
        Contract.objects_all
        .filter(id=int(contract_id), tenant_id=int(tenant_id))
        .prefetch_related("contract_shops__shop")
        .first()
    )


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


def _parse_dt(v):
    if not v:
        return None
    try:
        dt = parse_datetime(str(v))
        if dt and timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt
    except Exception:
        return None


def _safe_shop_id_for_tenant(shop_id, tenant_id: int):
    sid = _int_or_none(shop_id)
    if not sid:
        return None

    shop = Shop.objects_all.filter(id=sid, tenant_id=int(tenant_id)).first()
    return shop.id if shop else None


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
    contract_kind = str(meta.get("contract_kind") or "").strip().lower()

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
        "total_value": str(x.total_value or 0),
        "vat_percent": str(x.vat_percent or 0),
        "note": x.note or "",
        "meta": meta,
        "contract_kind": contract_kind,
        "shops": shops,
        "created_at": x.created_at.isoformat() if x.created_at else None,
        "updated_at": x.updated_at.isoformat() if x.updated_at else None,
    }


def _serialize_milestone(x: ContractMilestone) -> Dict[str, Any]:
    return {
        "id": x.id,
        "contract_id": x.contract_id,
        "company_id": x.company_id,
        "shop_id": x.shop_id,
        "title": x.title,
        "description": x.description or "",
        "kind": x.kind,
        "status": x.status,
        "due_at": x.due_at.isoformat() if x.due_at else None,
        "done_at": x.done_at.isoformat() if x.done_at else None,
        "sort_order": x.sort_order,
        "meta": x.meta or {},
    }


def _serialize_payment(x: ContractPayment) -> Dict[str, Any]:
    return {
        "id": x.id,
        "contract_id": x.contract_id,
        "milestone_id": x.milestone_id,
        "title": x.title,
        "amount": str(x.amount or 0),
        "vat_percent": str(x.vat_percent or 0),
        "vat_amount": str(x.vat_amount or 0),
        "total_amount": str(x.total_amount or 0),
        "due_at": x.due_at.isoformat() if x.due_at else None,
        "paid_amount": str(x.paid_amount or 0),
        "paid_at": x.paid_at.isoformat() if x.paid_at else None,
        "status": x.status,
        "note": x.note or "",
        "meta": x.meta or {},
    }


def _serialize_booking(x: ContractBookingItem) -> Dict[str, Any]:
    aired = bool((x.video_link or "").strip())
    return {
        "id": x.id,
        "contract_id": x.contract_id,
        "company_id": x.company_id,
        "shop_id": x.shop_id,
        "koc_name": x.koc_name,
        "koc_channel_name": x.koc_channel_name or "",
        "koc_channel_link": x.koc_channel_link or "",
        "booking_type": x.booking_type,
        "unit_price": str(x.unit_price or 0),
        "commission_percent": str(x.commission_percent or 0),
        "expected_post_count": x.expected_post_count or 0,
        "delivered_post_count": x.delivered_post_count or 0,
        "brand_amount": str(x.brand_amount or 0),
        "payout_amount": str(x.payout_amount or 0),
        "air_date": x.air_date.isoformat() if x.air_date else None,
        "video_link": x.video_link or "",
        "payout_due_at": x.payout_due_at.isoformat() if x.payout_due_at else None,
        "payout_paid_at": x.payout_paid_at.isoformat() if x.payout_paid_at else None,
        "payout_status": x.payout_status,
        "note": x.note or "",
        "meta": x.meta or {},
        "is_aired": aired,
    }


class ContractDetailCenterApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, contract_id: int):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        contract = _get_contract_or_none(contract_id, tenant_id)
        if not contract:
            return Response({"ok": False, "message": "Không tìm thấy hợp đồng"}, status=404)

        milestones = [
            _serialize_milestone(x)
            for x in ContractMilestone.objects_all.filter(
                tenant_id=int(tenant_id),
                contract_id=contract.id,
            ).order_by("sort_order", "id")
        ]

        payments = [
            _serialize_payment(x)
            for x in ContractPayment.objects_all.filter(
                tenant_id=int(tenant_id),
                contract_id=contract.id,
            ).order_by("due_at", "id")
        ]

        bookings = [
            _serialize_booking(x)
            for x in ContractBookingItem.objects_all.filter(
                tenant_id=int(tenant_id),
                contract_id=contract.id,
            ).order_by("id")
        ]

        booking_aired = len([x for x in bookings if x["is_aired"]])
        booking_not_aired = len([x for x in bookings if not x["is_aired"]])
        payout_paid = len([x for x in bookings if x["payout_status"] == "paid"])
        payout_pending = len([x for x in bookings if x["payout_status"] in ("pending", "cancelled") is False])  # kept compatible
        payout_pending = len([x for x in bookings if x["payout_status"] == "pending"])

        headline = {
            "milestones_total": len(milestones),
            "milestones_done": len([x for x in milestones if x["status"] == "done"]),
            "payments_total": len(payments),
            "payments_paid": len([x for x in payments if x["status"] == "paid"]),
            "payments_pending": len([x for x in payments if x["status"] in ("pending", "partial", "overdue")]),
            "bookings_total": len(bookings),
            "booking_aired": booking_aired,
            "booking_not_aired": booking_not_aired,
            "payout_paid": payout_paid,
            "payout_pending": payout_pending,
        }

        return Response(
            {
                "ok": True,
                "tenant_id": int(tenant_id),
                "headline": headline,
                "contract": _serialize_contract(contract),
                "milestones": milestones,
                "payments": payments,
                "bookings": bookings,
            }
        )


class ContractMilestoneCreateApi(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, contract_id: int):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        contract = _get_contract_or_none(contract_id, tenant_id)
        if not contract:
            return Response({"ok": False, "message": "Không tìm thấy hợp đồng"}, status=404)

        data = request.data or {}
        title = str(data.get("title") or "").strip()
        if not title:
            return Response({"ok": False, "message": "Thiếu tiêu đề milestone"}, status=400)

        kind = str(data.get("kind") or ContractMilestone.Kind.OTHER).strip()
        allowed_kinds = {x[0] for x in ContractMilestone.Kind.choices}
        if kind not in allowed_kinds:
            kind = ContractMilestone.Kind.OTHER

        shop_id = _safe_shop_id_for_tenant(data.get("shop_id"), tenant_id)

        item = ContractMilestone.objects_all.create(
            tenant_id=int(tenant_id),
            contract_id=contract.id,
            company_id=contract.company_id,
            shop_id=shop_id,
            title=title,
            description=str(data.get("description") or "").strip(),
            kind=kind,
            status=ContractMilestone.Status.TODO,
            due_at=_parse_dt(data.get("due_at")),
            sort_order=_int_or_none(data.get("sort_order")) or 1,
            meta={},
        )

        return Response({"ok": True, "item": _serialize_milestone(item)}, status=201)


class ContractMilestoneDoneApi(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, contract_id: int, milestone_id: int):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        contract = _get_contract_or_none(contract_id, tenant_id)
        if not contract:
            return Response({"ok": False, "message": "Không tìm thấy hợp đồng"}, status=404)

        item = ContractMilestone.objects_all.filter(
            tenant_id=int(tenant_id),
            contract_id=contract.id,
            id=int(milestone_id),
        ).first()
        if not item:
            return Response({"ok": False, "message": "Không tìm thấy milestone"}, status=404)

        item.status = ContractMilestone.Status.DONE
        if not item.done_at:
            item.done_at = timezone.now()
        item.save(update_fields=["status", "done_at", "updated_at"])

        return Response({"ok": True, "item": _serialize_milestone(item)})


class ContractPaymentCreateApi(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, contract_id: int):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        contract = _get_contract_or_none(contract_id, tenant_id)
        if not contract:
            return Response({"ok": False, "message": "Không tìm thấy hợp đồng"}, status=404)

        data = request.data or {}
        title = str(data.get("title") or "").strip()
        if not title:
            return Response({"ok": False, "message": "Thiếu tiêu đề payment"}, status=400)

        amount = _dec(data.get("amount"))
        vat_percent = _dec(data.get("vat_percent"), "0")
        vat_amount = (amount * vat_percent / Decimal("100")) if vat_percent > 0 else Decimal("0")
        total_amount = amount + vat_amount

        milestone_id = _int_or_none(data.get("milestone_id"))
        milestone = None
        if milestone_id:
            milestone = ContractMilestone.objects_all.filter(
                tenant_id=int(tenant_id),
                contract_id=contract.id,
                id=milestone_id,
            ).first()
            if not milestone:
                return Response({"ok": False, "message": "Milestone không thuộc hợp đồng này"}, status=400)

        item = ContractPayment.objects_all.create(
            tenant_id=int(tenant_id),
            contract_id=contract.id,
            milestone_id=milestone.id if milestone else None,
            title=title,
            amount=amount,
            vat_percent=vat_percent,
            vat_amount=vat_amount,
            total_amount=total_amount,
            due_at=_parse_dt(data.get("due_at")),
            status=ContractPayment.Status.PENDING,
            note=str(data.get("note") or "").strip(),
            meta={},
        )

        return Response({"ok": True, "item": _serialize_payment(item)}, status=201)


class ContractPaymentMarkPaidApi(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, contract_id: int, payment_id: int):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        contract = _get_contract_or_none(contract_id, tenant_id)
        if not contract:
            return Response({"ok": False, "message": "Không tìm thấy hợp đồng"}, status=404)

        item = ContractPayment.objects_all.filter(
            tenant_id=int(tenant_id),
            contract_id=contract.id,
            id=int(payment_id),
        ).first()
        if not item:
            return Response({"ok": False, "message": "Không tìm thấy payment"}, status=404)

        data = request.data or {}
        paid_amount = _dec(data.get("paid_amount"), str(item.total_amount or 0))
        if paid_amount < 0:
            paid_amount = Decimal("0")

        item.paid_amount = paid_amount
        item.paid_at = _parse_dt(data.get("paid_at")) or timezone.now()

        if paid_amount <= 0:
            item.status = ContractPayment.Status.PENDING
        elif paid_amount < (item.total_amount or Decimal("0")):
            item.status = ContractPayment.Status.PARTIAL
        else:
            item.status = ContractPayment.Status.PAID

        item.save(update_fields=["paid_amount", "paid_at", "status", "updated_at"])

        return Response({"ok": True, "item": _serialize_payment(item)})


class ContractBookingCreateApi(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, contract_id: int):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        contract = _get_contract_or_none(contract_id, tenant_id)
        if not contract:
            return Response({"ok": False, "message": "Không tìm thấy hợp đồng"}, status=404)

        data = request.data or {}
        koc_name = str(data.get("koc_name") or "").strip()
        if not koc_name:
            return Response({"ok": False, "message": "Thiếu tên KOC/KOL"}, status=400)

        booking_type = str(
            data.get("booking_type") or ContractBookingItem.BookingType.FREE_CAST
        ).strip()
        allowed_types = {x[0] for x in ContractBookingItem.BookingType.choices}
        if booking_type not in allowed_types:
            booking_type = ContractBookingItem.BookingType.FREE_CAST

        shop_id = _safe_shop_id_for_tenant(data.get("shop_id"), tenant_id)

        item = ContractBookingItem.objects_all.create(
            tenant_id=int(tenant_id),
            contract_id=contract.id,
            company_id=contract.company_id,
            shop_id=shop_id,
            koc_name=koc_name,
            koc_channel_name=str(data.get("koc_channel_name") or "").strip(),
            koc_channel_link=str(data.get("koc_channel_link") or "").strip(),
            booking_type=booking_type,
            unit_price=_dec(data.get("unit_price")),
            commission_percent=_dec(data.get("commission_percent")),
            expected_post_count=_int_or_none(data.get("expected_post_count")) or 1,
            delivered_post_count=_int_or_none(data.get("delivered_post_count")) or 0,
            brand_amount=_dec(data.get("brand_amount")),
            payout_amount=_dec(data.get("payout_amount")),
            air_date=_parse_dt(data.get("air_date")),
            video_link=str(data.get("video_link") or "").strip(),
            payout_due_at=_parse_dt(data.get("payout_due_at")),
            note=str(data.get("note") or "").strip(),
            payout_status=ContractBookingItem.PayoutStatus.PENDING,
            meta={
                "phone": str(data.get("phone") or "").strip(),
                "contact_note": str(data.get("contact_note") or "").strip(),
            },
        )

        return Response({"ok": True, "item": _serialize_booking(item)}, status=201)


class ContractBookingMarkAiredApi(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, contract_id: int, booking_id: int):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        contract = _get_contract_or_none(contract_id, tenant_id)
        if not contract:
            return Response({"ok": False, "message": "Không tìm thấy hợp đồng"}, status=404)

        item = ContractBookingItem.objects_all.filter(
            tenant_id=int(tenant_id),
            contract_id=contract.id,
            id=int(booking_id),
        ).first()
        if not item:
            return Response({"ok": False, "message": "Không tìm thấy booking"}, status=404)

        data = request.data or {}
        video_link = str(data.get("video_link") or item.video_link or "").strip()
        if not video_link:
            return Response({"ok": False, "message": "Cần video_link để đánh dấu đã air"}, status=400)

        delivered_post_count = _int_or_none(data.get("delivered_post_count"))
        if delivered_post_count is None:
            delivered_post_count = max(int(item.delivered_post_count or 0), 1)

        item.video_link = video_link
        item.air_date = _parse_dt(data.get("air_date")) or item.air_date or timezone.now()
        item.delivered_post_count = delivered_post_count
        item.save(update_fields=["video_link", "air_date", "delivered_post_count", "updated_at"])

        return Response({"ok": True, "item": _serialize_booking(item)})


class ContractBookingMarkPayoutPaidApi(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, contract_id: int, booking_id: int):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        contract = _get_contract_or_none(contract_id, tenant_id)
        if not contract:
            return Response({"ok": False, "message": "Không tìm thấy hợp đồng"}, status=404)

        item = ContractBookingItem.objects_all.filter(
            tenant_id=int(tenant_id),
            contract_id=contract.id,
            id=int(booking_id),
        ).first()
        if not item:
            return Response({"ok": False, "message": "Không tìm thấy booking"}, status=404)

        data = request.data or {}
        item.payout_paid_at = _parse_dt(data.get("payout_paid_at")) or timezone.now()
        item.payout_status = ContractBookingItem.PayoutStatus.PAID
        item.save(update_fields=["payout_paid_at", "payout_status", "updated_at"])

        return Response({"ok": True, "item": _serialize_booking(item)})