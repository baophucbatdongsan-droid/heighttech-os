from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.utils import timezone

from apps.contracts.models import ContractBookingItem, ContractMilestone, ContractPayment
from apps.work.models import WorkItem


def _to_decimal(v) -> Decimal:
    try:
        return Decimal(str(v or 0))
    except Exception:
        return Decimal("0")


@dataclass(frozen=True)
class AIDecisionEngineResult:
    headline: Dict[str, Any]
    items: List[Dict[str, Any]]


def build_ai_decisions(
    *,
    tenant_id: int,
    company_id: Optional[int] = None,
    shop_id: Optional[int] = None,
    project_id: Optional[int] = None,
    limit: int = 8,
) -> AIDecisionEngineResult:
    now = timezone.now()
    next_7d = now + timezone.timedelta(days=7)

    payment_qs = ContractPayment.objects_all.filter(tenant_id=int(tenant_id))
    milestone_qs = ContractMilestone.objects_all.filter(tenant_id=int(tenant_id))
    booking_qs = ContractBookingItem.objects_all.filter(tenant_id=int(tenant_id))
    work_qs = WorkItem.objects_all.filter(tenant_id=int(tenant_id))

    if company_id:
        payment_qs = payment_qs.filter(contract__company_id=int(company_id))
        milestone_qs = milestone_qs.filter(contract__company_id=int(company_id))
        booking_qs = booking_qs.filter(contract__company_id=int(company_id))
        work_qs = work_qs.filter(company_id=int(company_id))

    if shop_id:
        payment_qs = payment_qs.filter(contract__contract_shops__shop_id=int(shop_id)).distinct()
        milestone_qs = milestone_qs.filter(contract__contract_shops__shop_id=int(shop_id)).distinct()
        booking_qs = booking_qs.filter(shop_id=int(shop_id))
        work_qs = work_qs.filter(shop_id=int(shop_id))

    if project_id:
        work_qs = work_qs.filter(project_id=int(project_id))

    items: List[Dict[str, Any]] = []

    # 1. Công nợ quá hạn
    receivable_overdue = payment_qs.filter(
        status__in=[ContractPayment.Status.PENDING, ContractPayment.Status.PARTIAL],
        due_at__isnull=False,
        due_at__lt=now,
    )
    receivable_overdue_total = sum((_to_decimal(x.amount) for x in receivable_overdue), Decimal("0"))
    if receivable_overdue.exists():
        items.append(
            {
                "kind": "cash_collection",
                "priority": "critical",
                "title": "Cần thu hồi công nợ quá hạn",
                "summary": f"Có {receivable_overdue.count()} khoản thanh toán quá hạn, tổng khoảng {int(receivable_overdue_total):,} đ.".replace(",", "."),
                "action": "Ưu tiên nhắc thanh toán và xác nhận lịch thu tiền trong hôm nay.",
            }
        )

    # 2. Milestone quá hạn
    milestone_overdue = milestone_qs.filter(
        status__in=[ContractMilestone.Status.TODO, ContractMilestone.Status.DOING],
        due_at__isnull=False,
        due_at__lt=now,
    )
    if milestone_overdue.exists():
        items.append(
            {
                "kind": "milestone_execution",
                "priority": "critical",
                "title": "Milestone hợp đồng đang trễ",
                "summary": f"Có {milestone_overdue.count()} milestone quá hạn cần nghiệm thu / xử lý.",
                "action": "Rà soát milestone trễ và giao owner xử lý ngay trong Work OS.",
            }
        )

    # 3. Booking air sắp tới
    booking_air_soon = booking_qs.filter(
        air_date__isnull=False,
        air_date__gte=now,
        air_date__lte=next_7d,
    )
    if booking_air_soon.exists():
        items.append(
            {
                "kind": "booking_air",
                "priority": "warning",
                "title": "Booking KOC sắp tới lịch air",
                "summary": f"Có {booking_air_soon.count()} booking sẽ air trong 7 ngày tới.",
                "action": "Chốt nội dung, xác nhận KOC và kiểm tra lịch đăng trước hạn.",
            }
        )

    # 4. Booking quá air nhưng thiếu link
    booking_missing_link = booking_qs.filter(
        air_date__isnull=False,
        air_date__lt=now,
    ).filter(video_link__isnull=True) | booking_qs.filter(
        air_date__isnull=False,
        air_date__lt=now,
        video_link="",
    )
    booking_missing_link = booking_missing_link.distinct()
    if booking_missing_link.exists():
        items.append(
            {
                "kind": "booking_missing_link",
                "priority": "warning",
                "title": "Đã quá air date nhưng chưa có link video",
                "summary": f"Có {booking_missing_link.count()} booking chưa cập nhật link video sau air date.",
                "action": "Liên hệ KOC / account để lấy link và cập nhật hệ thống ngay.",
            }
        )

    # 5. Backlog work quá hạn
    backlog_overdue = work_qs.exclude(
        status__in=[WorkItem.Status.DONE, WorkItem.Status.CANCELLED]
    ).filter(
        due_at__isnull=False,
        due_at__lt=now,
    )
    if backlog_overdue.exists():
        items.append(
            {
                "kind": "work_backlog",
                "priority": "warning",
                "title": "Backlog công việc đang bị nghẽn",
                "summary": f"Có {backlog_overdue.count()} task quá hạn trong hệ thống.",
                "action": "Triage backlog, đẩy việc gấp sang owner phù hợp hoặc tách nhỏ đầu việc.",
            }
        )

    # 6. Payout KOC quá hạn
    payout_overdue = booking_qs.filter(
        payout_status=ContractBookingItem.PayoutStatus.PENDING,
        payout_due_at__isnull=False,
        payout_due_at__lt=now,
    )
    payout_overdue_total = sum((_to_decimal(x.payout_amount) for x in payout_overdue), Decimal("0"))
    if payout_overdue.exists():
        items.append(
            {
                "kind": "koc_payout",
                "priority": "critical",
                "title": "Payout KOC quá hạn",
                "summary": f"Có {payout_overdue.count()} payout quá hạn, tổng khoảng {int(payout_overdue_total):,} đ.".replace(",", "."),
                "action": "Ưu tiên xác nhận thanh toán KOC để tránh chậm lịch booking tiếp theo.",
            }
        )

    priority_rank = {"critical": 3, "warning": 2, "info": 1}
    items.sort(key=lambda x: (-priority_rank.get(x.get("priority", "info"), 0), x.get("title", "")))
    items = items[: max(1, int(limit or 8))]

    headline = {
        "ai_decision_total": len(items),
        "ai_decision_critical": len([x for x in items if x.get("priority") == "critical"]),
        "ai_decision_warning": len([x for x in items if x.get("priority") == "warning"]),
    }

    return AIDecisionEngineResult(headline=headline, items=items)