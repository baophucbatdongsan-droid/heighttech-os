from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from django.db import transaction
from django.utils import timezone

from apps.contracts.models import Contract, ContractMilestone, ContractPayment


def _to_decimal(v) -> Decimal:
    try:
        return Decimal(str(v or 0))
    except Exception:
        return Decimal("0")


def _money(v: Decimal) -> Decimal:
    return _to_decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _month_last_day(year: int, month: int) -> int:
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return (next_month - timezone.timedelta(days=1)).day


def _add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, _month_last_day(year, month))
    return date(year, month, day)


def _combine_local(d: Optional[date]) -> Optional[datetime]:
    if not d:
        return None
    dt = datetime.combine(d, time(23, 59, 59))
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _months_between_inclusive(start_date: Optional[date], end_date: Optional[date]) -> int:
    if not start_date or not end_date:
        return 1
    if end_date < start_date:
        return 1

    months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1
    return max(1, months)


def _build_month_points(start_date: Optional[date], end_date: Optional[date]) -> List[date]:
    if not start_date:
        return []

    count = _months_between_inclusive(start_date, end_date)
    arr: List[date] = []
    for i in range(count):
        arr.append(_add_months(start_date, i))
    return arr


def _clear_old_auto_rows(contract: Contract) -> None:
    ContractMilestone.objects_all.filter(
        contract_id=contract.id,
        tenant_id=contract.tenant_id,
        meta__auto_generated=True,
    ).delete()

    ContractPayment.objects_all.filter(
        contract_id=contract.id,
        tenant_id=contract.tenant_id,
        meta__auto_generated=True,
    ).delete()


@dataclass
class BuildResult:
    milestone_count: int
    payment_count: int


@transaction.atomic
def rebuild_contract_schedule(contract: Contract) -> BuildResult:
    """
    FINAL:
    - xoá toàn bộ milestone/payment auto-generated cũ
    - sinh lại theo type hợp đồng
    - operation/channel: chia theo tháng
    - booking: không auto payment tổng, vì booking thường theo từng KOC item
    - payment có tách amount / VAT / total_amount
    """
    contract = Contract.objects_all.select_for_update().get(id=contract.id)

    _clear_old_auto_rows(contract)

    ctype = (contract.contract_type or "").strip().lower()
    start_date = contract.start_date
    end_date = contract.end_date

    total_value = _money(contract.total_value or 0)      # tiền trước VAT
    vat_percent = _money(contract.vat_percent or 0)
    vat_multiplier = _to_decimal(vat_percent) / Decimal("100")

    milestone_count = 0
    payment_count = 0

    if ctype in {Contract.Type.OPERATION, Contract.Type.CHANNEL}:
        points = _build_month_points(start_date, end_date)
        if not points and start_date:
            points = [start_date]

        month_count = max(1, len(points))
        per_month_base = _money(total_value / Decimal(month_count)) if month_count > 0 else _money(total_value)

        allocated_base = Decimal("0.00")

        for idx, point in enumerate(points, start=1):
            is_last = idx == month_count

            ms_due = _combine_local(_add_months(point, 1) - timezone.timedelta(days=1))
            if not ms_due:
                ms_due = _combine_local(point)

            milestone_title = (
                f"Nghiệm thu tháng {idx}"
                if ctype == Contract.Type.OPERATION
                else f"Bàn giao / nghiệm thu tháng {idx}"
            )

            milestone_desc = f"Mốc tự động cho hợp đồng {contract.code} - tháng {idx}."

            milestone = ContractMilestone.objects_all.create(
                tenant_id=contract.tenant_id,
                contract_id=contract.id,
                company_id=contract.company_id,
                title=milestone_title,
                description=milestone_desc,
                kind=ContractMilestone.Kind.ACCEPTANCE,
                status=ContractMilestone.Status.TODO,
                due_at=ms_due,
                sort_order=idx,
                meta={
                    "auto_generated": True,
                    "schedule_kind": "monthly",
                    "month_no": idx,
                    "contract_type": ctype,
                },
            )
            milestone_count += 1

            if is_last:
                base_amount = _money(total_value - allocated_base)
            else:
                base_amount = per_month_base
                allocated_base += base_amount

            vat_amount = _money(base_amount * vat_multiplier)
            total_amount = _money(base_amount + vat_amount)

            pay_due = _combine_local(point)

            ContractPayment.objects_all.create(
                tenant_id=contract.tenant_id,
                contract_id=contract.id,
                milestone_id=milestone.id,
                title=f"Thanh toán tháng {idx}",
                amount=base_amount,
                vat_percent=vat_percent,
                vat_amount=vat_amount,
                total_amount=total_amount,
                due_at=pay_due,
                status=ContractPayment.Status.PENDING,
                note=f"Kỳ thanh toán tự động tháng {idx} cho hợp đồng {contract.code}",
                meta={
                    "auto_generated": True,
                    "schedule_kind": "monthly",
                    "month_no": idx,
                    "contract_type": ctype,
                },
            )
            payment_count += 1

    elif ctype == Contract.Type.BOOKING:
        # Booking không auto sinh payment tổng
        # vì payout chủ yếu đi theo từng KOC item / payout_due_at
        if start_date:
            ContractMilestone.objects_all.create(
                tenant_id=contract.tenant_id,
                contract_id=contract.id,
                company_id=contract.company_id,
                title="Theo dõi booking campaign",
                description=f"Mốc tổng theo dõi booking cho hợp đồng {contract.code}",
                kind=ContractMilestone.Kind.OTHER,
                status=ContractMilestone.Status.TODO,
                due_at=_combine_local(end_date or start_date),
                sort_order=1,
                meta={
                    "auto_generated": True,
                    "schedule_kind": "booking_summary",
                    "contract_type": ctype,
                },
            )
            milestone_count += 1

    return BuildResult(
        milestone_count=milestone_count,
        payment_count=payment_count,
    )