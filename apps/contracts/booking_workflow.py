from __future__ import annotations

from dataclasses import dataclass

from django.utils import timezone

from apps.contracts.models import ContractBookingItem
from apps.work.models import WorkItem


BOOKING_AIR_PREP_DAYS = 2


@dataclass(frozen=True)
class BookingWorkflowResult:
    prep_created: int = 0
    waiting_link_created: int = 0
    payout_created: int = 0
    auto_closed: int = 0


def _norm_dt(dt):
    if not dt:
        return None
    try:
        if timezone.is_naive(dt):
            return timezone.make_aware(dt, timezone.get_current_timezone())
        return dt
    except Exception:
        return dt


def _contract_type_label(contract_type: str) -> str:
    v = (contract_type or "").strip().lower()
    if v == "booking":
        return "Booking"
    if v == "channel":
        return "Xây kênh"
    if v == "operation":
        return "Vận hành"
    return "Hợp đồng"


def _task_title(stage: str, contract_code: str, koc_name: str) -> str:
    if stage == "prep_air":
        return f"[Booking][Chuẩn bị air] {contract_code} • {koc_name}"
    if stage == "waiting_link":
        return f"[Booking][Chờ link video] {contract_code} • {koc_name}"
    if stage == "waiting_payout":
        return f"[Booking][Chờ payout KOC] {contract_code} • {koc_name}"
    return f"[Booking][Workflow] {contract_code} • {koc_name}"


def _find_open_stage_task(*, tenant_id: int, item_id: int, stage: str):
    title_prefix = {
        "prep_air": "[Booking][Chuẩn bị air]",
        "waiting_link": "[Booking][Chờ link video]",
        "waiting_payout": "[Booking][Chờ payout KOC]",
    }.get(stage, "[Booking][")

    qs = WorkItem.objects_all.filter(
        tenant_id=int(tenant_id),
        title__startswith=title_prefix,
    ).exclude(status__in=[WorkItem.Status.DONE, WorkItem.Status.CANCELLED])

    if hasattr(WorkItem, "target_type") and hasattr(WorkItem, "target_id"):
        qs = qs.filter(target_type="contract_booking_item", target_id=int(item_id))

    return qs.order_by("-id").first()


def _ensure_stage_task(
    *,
    item: ContractBookingItem,
    stage: str,
    title: str,
    description: str,
    due_at,
    priority: int,
) -> bool:
    existed = _find_open_stage_task(
        tenant_id=int(item.tenant_id),
        item_id=int(item.id),
        stage=stage,
    )
    if existed:
        return False

    obj = WorkItem(
        tenant_id=int(item.tenant_id),
        title=title[:255],
        description=description or "",
        status=WorkItem.Status.TODO,
        priority=priority if priority in (1, 2, 3, 4) else 3,
        company_id=getattr(item.contract, "company_id", None) if getattr(item, "contract", None) else None,
        shop_id=getattr(item, "shop_id", None),
        project_id=None,
        due_at=due_at,
        created_by=None,
        requester=None,
        assignee=None,
        is_internal=False,
    )

    if hasattr(obj, "target_type"):
        obj.target_type = "contract_booking_item"
    if hasattr(obj, "target_id"):
        obj.target_id = int(item.id)
    if hasattr(obj, "type"):
        obj.type = WorkItem.Type.TASK

    obj.save()
    return True


def _close_stage_task_if_exists(*, tenant_id: int, item_id: int, stage: str) -> bool:
    obj = _find_open_stage_task(
        tenant_id=int(tenant_id),
        item_id=int(item_id),
        stage=stage,
    )
    if not obj:
        return False

    obj.status = WorkItem.Status.DONE
    obj.done_at = timezone.now()
    obj.save(update_fields=["status", "done_at", "updated_at"])
    return True


def _sync_one_item(item: ContractBookingItem) -> BookingWorkflowResult:
    now = timezone.now()
    air_date = _norm_dt(item.air_date)
    has_video_link = bool((item.video_link or "").strip())
    payout_pending = (item.payout_status or "").strip().lower() == ContractBookingItem.PayoutStatus.PENDING

    contract = getattr(item, "contract", None)
    contract_code = getattr(contract, "code", "") or f"HD{item.contract_id}"
    contract_type = getattr(contract, "contract_type", "") or ""
    _ = _contract_type_label(contract_type)  # giữ sẵn cho future, hiện title stage dùng Booking cứng
    koc_name = (item.koc_name or "").strip() or f"KOC#{item.id}"

    prep_created = 0
    waiting_link_created = 0
    payout_created = 0
    auto_closed = 0

    should_prep_air = False
    should_waiting_link = False
    should_waiting_payout = False

    if air_date:
        soon_dt = now + timezone.timedelta(days=BOOKING_AIR_PREP_DAYS)
        if now <= air_date <= soon_dt:
            should_prep_air = True

        if air_date < now and not has_video_link:
            should_waiting_link = True

    if has_video_link and payout_pending:
        should_waiting_payout = True

    if should_prep_air:
        title = _task_title("prep_air", contract_code, koc_name)
        desc = (
            f"Hợp đồng: {contract_code}\n"
            f"Booking item: {item.id}\n"
            f"KOC: {koc_name}\n"
            f"Air date: {air_date.strftime('%d/%m/%Y %H:%M') if air_date else 'Chưa có'}\n"
            f"Yêu cầu: chuẩn bị lịch air / xác nhận KOC / rà soát nội dung trước giờ đăng."
        )
        if _ensure_stage_task(
            item=item,
            stage="prep_air",
            title=title,
            description=desc,
            due_at=air_date,
            priority=3,
        ):
            prep_created += 1
    else:
        if _close_stage_task_if_exists(
            tenant_id=item.tenant_id,
            item_id=item.id,
            stage="prep_air",
        ):
            auto_closed += 1

    if should_waiting_link:
        title = _task_title("waiting_link", contract_code, koc_name)
        desc = (
            f"Hợp đồng: {contract_code}\n"
            f"Booking item: {item.id}\n"
            f"KOC: {koc_name}\n"
            f"Air date: {air_date.strftime('%d/%m/%Y %H:%M') if air_date else 'Chưa có'}\n"
            f"Link video hiện tại: chưa có\n"
            f"Yêu cầu: lấy link video sau khi air / cập nhật hệ thống."
        )
        if _ensure_stage_task(
            item=item,
            stage="waiting_link",
            title=title,
            description=desc,
            due_at=air_date,
            priority=4,
        ):
            waiting_link_created += 1
    else:
        if _close_stage_task_if_exists(
            tenant_id=item.tenant_id,
            item_id=item.id,
            stage="waiting_link",
        ):
            auto_closed += 1

    if should_waiting_payout:
        due_at = _norm_dt(item.payout_due_at) or air_date
        title = _task_title("waiting_payout", contract_code, koc_name)
        desc = (
            f"Hợp đồng: {contract_code}\n"
            f"Booking item: {item.id}\n"
            f"KOC: {koc_name}\n"
            f"Đã có link video: có\n"
            f"Payout status: {item.payout_status}\n"
            f"Payout due: {due_at.strftime('%d/%m/%Y %H:%M') if due_at else 'Chưa có'}\n"
            f"Yêu cầu: xác nhận payout và cập nhật trạng thái thanh toán KOC."
        )
        if _ensure_stage_task(
            item=item,
            stage="waiting_payout",
            title=title,
            description=desc,
            due_at=due_at,
            priority=3,
        ):
            payout_created += 1
    else:
        if _close_stage_task_if_exists(
            tenant_id=item.tenant_id,
            item_id=item.id,
            stage="waiting_payout",
        ):
            auto_closed += 1

    return BookingWorkflowResult(
        prep_created=prep_created,
        waiting_link_created=waiting_link_created,
        payout_created=payout_created,
        auto_closed=auto_closed,
    )


def run_booking_workflow() -> BookingWorkflowResult:
    prep_created = 0
    waiting_link_created = 0
    payout_created = 0
    auto_closed = 0

    qs = (
        ContractBookingItem.objects_all.select_related("contract", "shop")
        .order_by("id")
    )

    for item in qs:
        res = _sync_one_item(item)
        prep_created += res.prep_created
        waiting_link_created += res.waiting_link_created
        payout_created += res.payout_created
        auto_closed += res.auto_closed

    return BookingWorkflowResult(
        prep_created=prep_created,
        waiting_link_created=waiting_link_created,
        payout_created=payout_created,
        auto_closed=auto_closed,
    )