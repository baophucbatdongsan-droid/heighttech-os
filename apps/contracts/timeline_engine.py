from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, List, Optional

from django.db.models import Q
from django.utils import timezone

from apps.contracts.models import ContractBookingItem, ContractMilestone, ContractPayment


TIMELINE_LOOKAHEAD_DAYS = 14


@dataclass(frozen=True)
class TimelineBuildResult:
    items: List[Dict[str, Any]]
    headline: Dict[str, int]


def _contract_type_label(v: str) -> str:
    x = (v or "").strip().lower()
    if x == "booking":
        return "Booking"
    if x == "channel":
        return "Xây kênh"
    if x == "operation":
        return "Vận hành"
    return "Hợp đồng"


def _priority_for_due(due_at, now) -> str:
    if not due_at:
        return "info"
    if due_at < now:
        return "critical"
    if due_at <= now + timedelta(days=3):
        return "warning"
    return "info"


def _priority_rank(priority: str) -> int:
    p = (priority or "").strip().lower()
    if p == "critical":
        return 4
    if p == "warning":
        return 3
    if p == "info":
        return 2
    return 1


def _fmt_dt(dt) -> str:
    if not dt:
        return ""
    try:
        local_dt = timezone.localtime(dt)
        return local_dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        try:
            return dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            return str(dt)


def _scope_payment_qs(*, tenant_id: int, company_id=None, shop_id=None):
    qs = ContractPayment.objects_all.select_related("contract").filter(
        tenant_id=int(tenant_id)
    )

    if company_id:
        qs = qs.filter(contract__company_id=int(company_id))

    if shop_id:
        qs = qs.filter(contract__contract_shops__shop_id=int(shop_id)).distinct()

    return qs


def _scope_milestone_qs(*, tenant_id: int, company_id=None, shop_id=None):
    qs = ContractMilestone.objects_all.select_related("contract").filter(
        tenant_id=int(tenant_id)
    )

    if company_id:
        qs = qs.filter(contract__company_id=int(company_id))

    if shop_id:
        qs = qs.filter(
            Q(shop_id=int(shop_id)) | Q(contract__contract_shops__shop_id=int(shop_id))
        ).distinct()

    return qs


def _scope_booking_qs(*, tenant_id: int, company_id=None, shop_id=None):
    qs = ContractBookingItem.objects_all.select_related("contract", "shop").filter(
        tenant_id=int(tenant_id)
    )

    if company_id:
        qs = qs.filter(contract__company_id=int(company_id))

    if shop_id:
        qs = qs.filter(shop_id=int(shop_id))

    return qs


def build_contract_timeline(
    *,
    tenant_id: int,
    company_id=None,
    shop_id=None,
    project_id=None,  # giữ đồng bộ API scope, hiện contracts chưa dùng project
    limit: int = 12,
) -> TimelineBuildResult:
    now = timezone.now()
    lookahead = now + timedelta(days=TIMELINE_LOOKAHEAD_DAYS)

    items: List[Dict[str, Any]] = []

    payment_qs = _scope_payment_qs(
        tenant_id=tenant_id,
        company_id=company_id,
        shop_id=shop_id,
    ).filter(status__in=[ContractPayment.Status.PENDING, ContractPayment.Status.PARTIAL])

    for p in payment_qs:
        contract = getattr(p, "contract", None)
        if not contract:
            continue

        due_at = p.due_at
        if not due_at:
            continue

        if due_at > lookahead:
            continue

        ctype_label = _contract_type_label(getattr(contract, "contract_type", ""))
        priority = _priority_for_due(due_at, now)

        if due_at < now:
            title = f"[{ctype_label}] Thanh toán quá hạn"
            summary = f"{contract.code} • {p.title} • quá hạn từ {_fmt_dt(due_at)}"
            state = "overdue"
        else:
            title = f"[{ctype_label}] Thanh toán sắp đến hạn"
            summary = f"{contract.code} • {p.title} • hạn {_fmt_dt(due_at)}"
            state = "due_soon"

        items.append(
            {
                "id": f"payment:{p.id}",
                "kind": "contract_payment",
                "priority": priority,
                "priority_rank": _priority_rank(priority),
                "state": state,
                "title": title,
                "summary": summary,
                "contract_id": contract.id,
                "contract_code": contract.code,
                "contract_type": getattr(contract, "contract_type", ""),
                "company_id": getattr(contract, "company_id", None),
                "shop_id": shop_id,
                "entity_id": p.id,
                "target_type": "contract_payment",
                "target_id": p.id,
                "due_at": due_at.isoformat() if due_at else None,
                "sort_due_at": due_at,
            }
        )

    milestone_qs = _scope_milestone_qs(
        tenant_id=tenant_id,
        company_id=company_id,
        shop_id=shop_id,
    ).filter(status__in=[ContractMilestone.Status.TODO, ContractMilestone.Status.DOING])

    for m in milestone_qs:
        contract = getattr(m, "contract", None)
        if not contract:
            continue

        due_at = m.due_at
        if not due_at:
            continue

        if due_at > lookahead:
            continue

        ctype_label = _contract_type_label(getattr(contract, "contract_type", ""))
        priority = _priority_for_due(due_at, now)

        if due_at < now:
            title = f"[{ctype_label}] Mốc hợp đồng quá hạn"
            summary = f"{contract.code} • {m.title} • quá hạn từ {_fmt_dt(due_at)}"
            state = "overdue"
        else:
            title = f"[{ctype_label}] Mốc hợp đồng sắp đến hạn"
            summary = f"{contract.code} • {m.title} • hạn {_fmt_dt(due_at)}"
            state = "due_soon"

        items.append(
            {
                "id": f"milestone:{m.id}",
                "kind": "contract_milestone",
                "priority": priority,
                "priority_rank": _priority_rank(priority),
                "state": state,
                "title": title,
                "summary": summary,
                "contract_id": contract.id,
                "contract_code": contract.code,
                "contract_type": getattr(contract, "contract_type", ""),
                "company_id": getattr(contract, "company_id", None),
                "shop_id": getattr(m, "shop_id", None),
                "entity_id": m.id,
                "target_type": "contract_milestone",
                "target_id": m.id,
                "due_at": due_at.isoformat() if due_at else None,
                "sort_due_at": due_at,
            }
        )

    booking_qs = _scope_booking_qs(
        tenant_id=tenant_id,
        company_id=company_id,
        shop_id=shop_id,
    )

    for b in booking_qs:
        contract = getattr(b, "contract", None)
        if not contract:
            continue

        ctype_label = _contract_type_label(getattr(contract, "contract_type", ""))
        has_video_link = bool((b.video_link or "").strip())

        if b.air_date and b.air_date <= lookahead:
            due_at = b.air_date
            priority = _priority_for_due(due_at, now)

            if due_at < now and not has_video_link:
                title = f"[{ctype_label}] Đã quá air date nhưng chưa có link"
                summary = f"{contract.code} • {b.koc_name} • air date {_fmt_dt(due_at)}"
                state = "air_passed_no_link"
                items.append(
                    {
                        "id": f"booking-air:{b.id}",
                        "kind": "contract_booking_item",
                        "priority": "warning",
                        "priority_rank": _priority_rank("warning"),
                        "state": state,
                        "title": title,
                        "summary": summary,
                        "contract_id": contract.id,
                        "contract_code": contract.code,
                        "contract_type": getattr(contract, "contract_type", ""),
                        "company_id": getattr(contract, "company_id", None),
                        "shop_id": getattr(b, "shop_id", None),
                        "entity_id": b.id,
                        "target_type": "contract_booking_item",
                        "target_id": b.id,
                        "due_at": due_at.isoformat() if due_at else None,
                        "sort_due_at": due_at,
                    }
                )
            elif now <= due_at <= lookahead:
                title = f"[{ctype_label}] Video KOC sắp air"
                summary = f"{contract.code} • {b.koc_name} • air date {_fmt_dt(due_at)}"
                state = "air_soon"
                items.append(
                    {
                        "id": f"booking-air:{b.id}",
                        "kind": "contract_booking_item",
                        "priority": priority,
                        "priority_rank": _priority_rank(priority),
                        "state": state,
                        "title": title,
                        "summary": summary,
                        "contract_id": contract.id,
                        "contract_code": contract.code,
                        "contract_type": getattr(contract, "contract_type", ""),
                        "company_id": getattr(contract, "company_id", None),
                        "shop_id": getattr(b, "shop_id", None),
                        "entity_id": b.id,
                        "target_type": "contract_booking_item",
                        "target_id": b.id,
                        "due_at": due_at.isoformat() if due_at else None,
                        "sort_due_at": due_at,
                    }
                )

        if b.payout_due_at and (b.payout_status or "").strip().lower() == ContractBookingItem.PayoutStatus.PENDING:
            due_at = b.payout_due_at
            if due_at <= lookahead:
                priority = _priority_for_due(due_at, now)

                if due_at < now:
                    title = f"[{ctype_label}] Payout KOC quá hạn"
                    summary = f"{contract.code} • {b.koc_name} • quá hạn từ {_fmt_dt(due_at)}"
                    state = "payout_overdue"
                else:
                    title = f"[{ctype_label}] Payout KOC sắp đến hạn"
                    summary = f"{contract.code} • {b.koc_name} • hạn {_fmt_dt(due_at)}"
                    state = "payout_due_soon"

                items.append(
                    {
                        "id": f"booking-payout:{b.id}",
                        "kind": "contract_booking_item",
                        "priority": priority,
                        "priority_rank": _priority_rank(priority),
                        "state": state,
                        "title": title,
                        "summary": summary,
                        "contract_id": contract.id,
                        "contract_code": contract.code,
                        "contract_type": getattr(contract, "contract_type", ""),
                        "company_id": getattr(contract, "company_id", None),
                        "shop_id": getattr(b, "shop_id", None),
                        "entity_id": b.id,
                        "target_type": "contract_booking_item",
                        "target_id": b.id,
                        "due_at": due_at.isoformat() if due_at else None,
                        "sort_due_at": due_at,
                    }
                )

    items.sort(
        key=lambda x: (
            -int(x.get("priority_rank") or 0),
            x.get("sort_due_at") or now + timedelta(days=3650),
            str(x.get("title") or ""),
        )
    )

    final_items = []
    for x in items[: max(1, int(limit or 12))]:
        y = dict(x)
        y.pop("sort_due_at", None)
        y.pop("priority_rank", None)
        final_items.append(y)

    headline = {
        "contract_timeline_total": len(final_items),
        "contract_timeline_critical": len([x for x in final_items if x.get("priority") == "critical"]),
        "contract_timeline_warning": len([x for x in final_items if x.get("priority") == "warning"]),
        "contract_timeline_info": len([x for x in final_items if x.get("priority") == "info"]),
    }

    return TimelineBuildResult(items=final_items, headline=headline)