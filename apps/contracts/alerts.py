from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from django.db.models import Q
from django.utils import timezone

from apps.contracts.models import ContractBookingItem, ContractMilestone, ContractPayment
from apps.os.models import OSNotification
from apps.work.models import WorkItem


CONTRACT_SOON_DAYS = 3
BOOKING_PAYOUT_SOON_DAYS = 3
BOOKING_AIR_SOON_DAYS = 2


@dataclass(frozen=True)
class AlertRunResult:
    payments_due_today: int = 0
    payments_overdue: int = 0
    milestones_due_today: int = 0
    milestones_overdue: int = 0
    booking_payout_overdue: int = 0
    booking_air_passed_no_link: int = 0
    created_notifications: int = 0
    created_tasks: int = 0


def _norm_dt(dt):
    if not dt:
        return None
    try:
        if timezone.is_naive(dt):
            return timezone.make_aware(dt, timezone.get_current_timezone())
        return dt
    except Exception:
        return dt


def _money(v) -> str:
    try:
        return str(Decimal(str(v or 0)).quantize(Decimal("0.01")))
    except Exception:
        return "0.00"


def _today_bounds():
    now = timezone.now()
    local_now = timezone.localtime(now)
    start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = local_now.replace(hour=23, minute=59, second=59, microsecond=999999)
    return start, end, now


def _create_os_notification_once(
    *,
    tenant_id: int,
    company_id,
    shop_id,
    severity: str,
    tieu_de: str,
    noi_dung: str,
    entity_kind: str,
    entity_id: int,
    dedupe_code: str,
    meta: Optional[dict] = None,
) -> bool:
    today = timezone.localdate()

    existed = OSNotification.objects_all.filter(
        tenant_id=int(tenant_id),
        entity_kind=entity_kind,
        entity_id=int(entity_id),
        tieu_de=tieu_de,
        created_at__date=today,
    ).filter(
        Q(meta__dedupe_code=dedupe_code) | Q(meta__dedupe_code__isnull=True)
    ).exists()

    if existed:
        return False

    OSNotification.objects_all.create(
        tenant_id=int(tenant_id),
        company_id=company_id,
        shop_id=shop_id,
        target_user=None,
        target_role="",
        tieu_de=tieu_de,
        noi_dung=noi_dung,
        severity=(severity or "info").strip().lower() or "info",
        entity_kind=entity_kind,
        entity_id=int(entity_id),
        meta={
            **(meta or {}),
            "dedupe_code": dedupe_code,
        },
        status=OSNotification.Status.NEW,
    )
    return True


def _find_open_task_by_title(*, tenant_id: int, title: str):
    return (
        WorkItem.objects_all.filter(
            tenant_id=int(tenant_id),
            title=title,
        )
        .exclude(status__in=[WorkItem.Status.DONE, WorkItem.Status.CANCELLED])
        .order_by("-id")
        .first()
    )


def _ensure_work_task(
    *,
    tenant_id: int,
    title: str,
    description: str,
    company_id=None,
    shop_id=None,
    project_id=None,
    due_at=None,
    priority: int = 3,
    target_type: str = "",
    target_id=None,
) -> bool:
    """
    Không tạo trùng nếu đang có task mở cùng title.
    """
    existed = _find_open_task_by_title(tenant_id=int(tenant_id), title=title)
    if existed:
        return False

    obj = WorkItem(
        tenant_id=int(tenant_id),
        title=title[:255],
        description=description or "",
        status=WorkItem.Status.TODO,
        priority=priority if priority in (1, 2, 3, 4) else 3,
        company_id=company_id,
        shop_id=shop_id,
        project_id=project_id,
        due_at=due_at,
        created_by=None,
        requester=None,
        assignee=None,
        is_internal=False,
    )

    if hasattr(obj, "target_type"):
        obj.target_type = (target_type or "").strip()

    if hasattr(obj, "target_id") and target_id:
        obj.target_id = int(target_id)

    if hasattr(obj, "type"):
        obj.type = WorkItem.Type.TASK

    obj.save()
    return True


def _handle_contract_payment_alerts(start_today, end_today, now) -> tuple[int, int, int, int]:
    created_notifications = 0
    created_tasks = 0
    payments_due_today = 0
    payments_overdue = 0

    qs = (
        ContractPayment.objects_all.select_related("contract")
        .filter(status__in=[ContractPayment.Status.PENDING, ContractPayment.Status.PARTIAL])
        .order_by("due_at", "id")
    )

    for p in qs:
        due_at = _norm_dt(p.due_at)
        if not due_at:
            continue

        contract = getattr(p, "contract", None)
        if not contract:
            continue

        ctype = (getattr(contract, "contract_type", "") or "").lower()
        if ctype == "booking":
            contract_prefix = "[Booking]"
        elif ctype == "channel":
            contract_prefix = "[Xây kênh]"
        elif ctype == "operation":
            contract_prefix = "[Vận hành]"
        else:
            contract_prefix = "[Hợp đồng]"

        company_id = getattr(contract, "company_id", None)

        if start_today <= due_at <= end_today:
            payments_due_today += 1

            tieu_de = "Thanh toán hợp đồng đến hạn hôm nay"
            noi_dung = (
                f"{contract.code} • {p.title} • đến hạn {due_at.strftime('%d/%m/%Y %H:%M')} • "
                f"số tiền {_money(getattr(p, 'amount', 0))}"
            )
            dedupe_code = f"contract-payment-due-today:{p.id}:{timezone.localdate().isoformat()}"

            if _create_os_notification_once(
                tenant_id=p.tenant_id,
                company_id=company_id,
                shop_id=None,
                severity="warning",
                tieu_de=tieu_de,
                noi_dung=noi_dung,
                entity_kind="contract_payment",
                entity_id=p.id,
                dedupe_code=dedupe_code,
                meta={
                    "contract_id": contract.id,
                    "contract_code": contract.code,
                    "payment_id": p.id,
                    "due_at": due_at.isoformat(),
                    "amount": _money(getattr(p, "amount", 0)),
                    "status": p.status,
                    "alert_kind": "payment_due_today",
                },
            ):
                created_notifications += 1

            task_title = f"[Đến hạn thanh toán HĐ] {contract.code} • {p.title}"
            task_desc = (
                f"Hợp đồng: {contract.code}\n"
                f"Nội dung: {p.title}\n"
                f"Trạng thái payment: {p.status}\n"
                f"Đến hạn: {due_at.strftime('%d/%m/%Y %H:%M')}\n"
                f"Số tiền: {_money(getattr(p, 'amount', 0))}\n"
                f"Yêu cầu: kiểm tra thanh toán / nhắc khách / cập nhật trạng thái."
            )

            if _ensure_work_task(
                tenant_id=p.tenant_id,
                title=task_title,
                description=task_desc,
                company_id=company_id,
                shop_id=None,
                project_id=None,
                due_at=due_at,
                priority=3,
                target_type="contract_payment",
                target_id=p.id,
            ):
                created_tasks += 1

        elif due_at < now:
            payments_overdue += 1

            tieu_de = "Thanh toán hợp đồng quá hạn"
            noi_dung = (
                f"{contract.code} • {p.title} • quá hạn từ {due_at.strftime('%d/%m/%Y %H:%M')} • "
                f"số tiền {_money(getattr(p, 'amount', 0))}"
            )
            dedupe_code = f"contract-payment-overdue:{p.id}:{timezone.localdate().isoformat()}"

            if _create_os_notification_once(
                tenant_id=p.tenant_id,
                company_id=company_id,
                shop_id=None,
                severity="critical",
                tieu_de=tieu_de,
                noi_dung=noi_dung,
                entity_kind="contract_payment",
                entity_id=p.id,
                dedupe_code=dedupe_code,
                meta={
                    "contract_id": contract.id,
                    "contract_code": contract.code,
                    "payment_id": p.id,
                    "due_at": due_at.isoformat(),
                    "amount": _money(getattr(p, "amount", 0)),
                    "status": p.status,
                    "alert_kind": "payment_overdue",
                },
            ):
                created_notifications += 1

            task_title = f"{contract_prefix}[Quá hạn thanh toán] {contract.code} • {p.title}"
            task_desc = (
                f"Hợp đồng: {contract.code}\n"
                f"Nội dung: {p.title}\n"
                f"Trạng thái payment: {p.status}\n"
                f"Quá hạn từ: {due_at.strftime('%d/%m/%Y %H:%M')}\n"
                f"Số tiền: {_money(getattr(p, 'amount', 0))}\n"
                f"Yêu cầu: xử lý gấp thanh toán hợp đồng."
            )

            if _ensure_work_task(
                tenant_id=p.tenant_id,
                title=task_title,
                description=task_desc,
                company_id=company_id,
                shop_id=None,
                project_id=None,
                due_at=due_at,
                priority=4,
                target_type="contract_payment",
                target_id=p.id,
            ):
                created_tasks += 1

    return payments_due_today, payments_overdue, created_notifications, created_tasks


def _handle_contract_milestone_alerts(start_today, end_today, now) -> tuple[int, int, int, int]:
    created_notifications = 0
    created_tasks = 0
    milestones_due_today = 0
    milestones_overdue = 0

    qs = (
        ContractMilestone.objects_all.select_related("contract", "shop")
        .filter(status__in=[ContractMilestone.Status.TODO, ContractMilestone.Status.DOING])
        .order_by("due_at", "id")
    )

    for m in qs:
        due_at = _norm_dt(m.due_at)
        if not due_at:
            continue

        contract = getattr(m, "contract", None)
        if not contract:
            continue

        ctype = (getattr(contract, "contract_type", "") or "").lower()
        if ctype == "booking":
            contract_prefix = "[Booking]"
        elif ctype == "channel":
            contract_prefix = "[Xây kênh]"
        elif ctype == "operation":
            contract_prefix = "[Vận hành]"
        else:
            contract_prefix = "[Hợp đồng]"

        company_id = getattr(contract, "company_id", None)
        shop_id = getattr(m, "shop_id", None)

        if start_today <= due_at <= end_today:
            milestones_due_today += 1

            tieu_de = "Mốc hợp đồng đến hạn hôm nay"
            noi_dung = f"{contract.code} • {m.title} • đến hạn {due_at.strftime('%d/%m/%Y %H:%M')}"
            dedupe_code = f"contract-milestone-due-today:{m.id}:{timezone.localdate().isoformat()}"

            if _create_os_notification_once(
                tenant_id=m.tenant_id,
                company_id=company_id,
                shop_id=shop_id,
                severity="warning",
                tieu_de=tieu_de,
                noi_dung=noi_dung,
                entity_kind="contract_milestone",
                entity_id=m.id,
                dedupe_code=dedupe_code,
                meta={
                    "contract_id": contract.id,
                    "contract_code": contract.code,
                    "milestone_id": m.id,
                    "due_at": due_at.isoformat(),
                    "status": m.status,
                    "alert_kind": "milestone_due_today",
                },
            ):
                created_notifications += 1

            task_title = f"[Đến hạn mốc HĐ] {contract.code} • {m.title}"
            task_desc = (
                f"Hợp đồng: {contract.code}\n"
                f"Milestone: {m.title}\n"
                f"Loại: {m.kind}\n"
                f"Trạng thái milestone: {m.status}\n"
                f"Đến hạn: {due_at.strftime('%d/%m/%Y %H:%M')}\n"
                f"Yêu cầu: kiểm tra nghiệm thu / bàn giao / điều kiện thanh toán."
            )

            if _ensure_work_task(
                tenant_id=m.tenant_id,
                title=task_title,
                description=task_desc,
                company_id=company_id,
                shop_id=shop_id,
                project_id=None,
                due_at=due_at,
                priority=3,
                target_type="contract_milestone",
                target_id=m.id,
            ):
                created_tasks += 1

        elif due_at < now:
            milestones_overdue += 1

            tieu_de = "Mốc hợp đồng quá hạn"
            noi_dung = f"{contract.code} • {m.title} • quá hạn từ {due_at.strftime('%d/%m/%Y %H:%M')}"
            dedupe_code = f"contract-milestone-overdue:{m.id}:{timezone.localdate().isoformat()}"

            if _create_os_notification_once(
                tenant_id=m.tenant_id,
                company_id=company_id,
                shop_id=shop_id,
                severity="critical",
                tieu_de=tieu_de,
                noi_dung=noi_dung,
                entity_kind="contract_milestone",
                entity_id=m.id,
                dedupe_code=dedupe_code,
                meta={
                    "contract_id": contract.id,
                    "contract_code": contract.code,
                    "milestone_id": m.id,
                    "due_at": due_at.isoformat(),
                    "status": m.status,
                    "alert_kind": "milestone_overdue",
                },
            ):
                created_notifications += 1

            task_title = f"{contract_prefix}[Quá hạn mốc] {contract.code} • {m.title}"
            task_desc = (
                f"Hợp đồng: {contract.code}\n"
                f"Milestone: {m.title}\n"
                f"Loại: {m.kind}\n"
                f"Trạng thái milestone: {m.status}\n"
                f"Quá hạn từ: {due_at.strftime('%d/%m/%Y %H:%M')}\n"
                f"Yêu cầu: xử lý gấp milestone / nghiệm thu / bàn giao."
            )

            if _ensure_work_task(
                tenant_id=m.tenant_id,
                title=task_title,
                description=task_desc,
                company_id=company_id,
                shop_id=shop_id,
                project_id=None,
                due_at=due_at,
                priority=4,
                target_type="contract_milestone",
                target_id=m.id,
            ):
                created_tasks += 1

    return milestones_due_today, milestones_overdue, created_notifications, created_tasks


def _handle_booking_payout_overdue(now) -> tuple[int, int, int]:
    created_notifications = 0
    created_tasks = 0
    payout_overdue = 0

    qs = (
        ContractBookingItem.objects_all.select_related("contract", "shop")
        .filter(payout_status=ContractBookingItem.PayoutStatus.PENDING)
        .order_by("payout_due_at", "id")
    )

    for item in qs:
        payout_due_at = _norm_dt(item.payout_due_at)
        if not payout_due_at or payout_due_at >= now:
            continue

        contract = getattr(item, "contract", None)
        if not contract:
            continue

        ctype = (getattr(contract, "contract_type", "") or "").lower()
        if ctype == "booking":
            contract_prefix = "[Booking]"
        elif ctype == "channel":
            contract_prefix = "[Xây kênh]"
        elif ctype == "operation":
            contract_prefix = "[Vận hành]"
        else:
            contract_prefix = "[Hợp đồng]"

        payout_overdue += 1

        company_id = getattr(contract, "company_id", None)
        shop_id = getattr(item, "shop_id", None)

        tieu_de = "Thanh toán KOC quá hạn"
        noi_dung = (
            f"{contract.code} • {item.koc_name} • quá hạn từ {payout_due_at.strftime('%d/%m/%Y %H:%M')} • "
            f"payout {_money(item.payout_amount)}"
        )
        dedupe_code = f"booking-payout-overdue:{item.id}:{timezone.localdate().isoformat()}"

        if _create_os_notification_once(
            tenant_id=item.tenant_id,
            company_id=company_id,
            shop_id=shop_id,
            severity="critical",
            tieu_de=tieu_de,
            noi_dung=noi_dung,
            entity_kind="contract_booking_item",
            entity_id=item.id,
            dedupe_code=dedupe_code,
            meta={
                "contract_id": contract.id,
                "contract_code": contract.code,
                "booking_item_id": item.id,
                "koc_name": item.koc_name,
                "payout_due_at": payout_due_at.isoformat(),
                "payout_amount": _money(item.payout_amount),
                "alert_kind": "booking_payout_overdue",
            },
        ):
            created_notifications += 1

        task_title = f"{contract_prefix}[Quá hạn payout KOC] {contract.code} • {item.koc_name}"
        task_desc = (
            f"Hợp đồng: {contract.code}\n"
            f"KOC: {item.koc_name}\n"
            f"Payout quá hạn từ: {payout_due_at.strftime('%d/%m/%Y %H:%M')}\n"
            f"Số tiền payout: {_money(item.payout_amount)}\n"
            f"Yêu cầu: kiểm tra thanh toán KOC / xác nhận chuyển khoản."
        )

        if _ensure_work_task(
            tenant_id=item.tenant_id,
            title=task_title,
            description=task_desc,
            company_id=company_id,
            shop_id=shop_id,
            project_id=None,
            due_at=payout_due_at,
            priority=4,
            target_type="contract_booking_item",
            target_id=item.id,
        ):
            created_tasks += 1

    return payout_overdue, created_notifications, created_tasks


def _handle_booking_air_passed_no_link(now) -> tuple[int, int, int]:
    created_notifications = 0
    created_tasks = 0
    air_passed_no_link = 0

    qs = (
        ContractBookingItem.objects_all.select_related("contract", "shop")
        .filter(air_date__isnull=False)
        .order_by("air_date", "id")
    )

    for item in qs:
        air_date = _norm_dt(item.air_date)
        if not air_date or air_date >= now:
            continue

        has_video_link = bool((item.video_link or "").strip())
        if has_video_link:
            continue

        contract = getattr(item, "contract", None)
        if not contract:
            continue

        ctype = (getattr(contract, "contract_type", "") or "").lower()
        if ctype == "booking":
            contract_prefix = "[Booking]"
        elif ctype == "channel":
            contract_prefix = "[Xây kênh]"
        elif ctype == "operation":
            contract_prefix = "[Vận hành]"
        else:
            contract_prefix = "[Hợp đồng]"

        air_passed_no_link += 1

        company_id = getattr(contract, "company_id", None)
        shop_id = getattr(item, "shop_id", None)

        tieu_de = "Đã quá air date nhưng chưa có link video"
        noi_dung = f"{contract.code} • {item.koc_name} • air date {air_date.strftime('%d/%m/%Y %H:%M')}"
        dedupe_code = f"booking-air-passed-no-link:{item.id}:{timezone.localdate().isoformat()}"

        if _create_os_notification_once(
            tenant_id=item.tenant_id,
            company_id=company_id,
            shop_id=shop_id,
            severity="warning",
            tieu_de=tieu_de,
            noi_dung=noi_dung,
            entity_kind="contract_booking_item",
            entity_id=item.id,
            dedupe_code=dedupe_code,
            meta={
                "contract_id": contract.id,
                "contract_code": contract.code,
                "booking_item_id": item.id,
                "koc_name": item.koc_name,
                "air_date": air_date.isoformat(),
                "video_link": item.video_link or "",
                "alert_kind": "booking_air_passed_no_link",
            },
        ):
            created_notifications += 1

        task_title = f"{contract_prefix}[Thiếu link video] {contract.code} • {item.koc_name}"
        task_desc = (
            f"Hợp đồng: {contract.code}\n"
            f"KOC: {item.koc_name}\n"
            f"Air date: {air_date.strftime('%d/%m/%Y %H:%M')}\n"
            f"Link video hiện tại: chưa có\n"
            f"Yêu cầu: nhắc KOC / cập nhật link video / kiểm tra trạng thái booking."
        )

        if _ensure_work_task(
            tenant_id=item.tenant_id,
            title=task_title,
            description=task_desc,
            company_id=company_id,
            shop_id=shop_id,
            project_id=None,
            due_at=air_date,
            priority=3,
            target_type="contract_booking_item",
            target_id=item.id,
        ):
            created_tasks += 1

    return air_passed_no_link, created_notifications, created_tasks


def run_contract_alerts() -> AlertRunResult:
    start_today, end_today, now = _today_bounds()

    payments_due_today, payments_overdue, n1, t1 = _handle_contract_payment_alerts(
        start_today, end_today, now
    )
    milestones_due_today, milestones_overdue, n2, t2 = _handle_contract_milestone_alerts(
        start_today, end_today, now
    )
    booking_payout_overdue, n3, t3 = _handle_booking_payout_overdue(now)
    booking_air_passed_no_link, n4, t4 = _handle_booking_air_passed_no_link(now)

    return AlertRunResult(
        payments_due_today=payments_due_today,
        payments_overdue=payments_overdue,
        milestones_due_today=milestones_due_today,
        milestones_overdue=milestones_overdue,
        booking_payout_overdue=booking_payout_overdue,
        booking_air_passed_no_link=booking_air_passed_no_link,
        created_notifications=(n1 + n2 + n3 + n4),
        created_tasks=(t1 + t2 + t3 + t4),
    )