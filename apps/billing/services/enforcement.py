from __future__ import annotations

from datetime import timedelta
from django.utils import timezone

from apps.billing.models import Invoice
from apps.tenants.models import Tenant
from apps.core.audit import log_change


def enforce_suspensions(grace_days: int = 7) -> int:
    """
    Level 18:
    - Nếu tenant có invoice FINAL (hoặc OVERDUE) của tháng trước mà chưa PAID sau grace_days => SUSPENDED
    """
    today = timezone.localdate()
    cutoff = today - timedelta(days=int(grace_days))

    # Nếu bạn có PAID: chỉ suspend những invoice chưa PAID
    has_paid = hasattr(Invoice.Status, "PAID")
    paid_value = Invoice.Status.PAID if has_paid else None

    # Chỉ xét invoice FINAL (production). Nếu bạn dùng OVERDUE thì mở rộng.
    statuses_to_check = []
    if hasattr(Invoice.Status, "FINAL"):
        statuses_to_check.append(Invoice.Status.FINAL)
    if hasattr(Invoice.Status, "OVERDUE"):
        statuses_to_check.append(Invoice.Status.OVERDUE)

    if not statuses_to_check:
        return 0

    qs = Invoice.objects.select_related("tenant").filter(
        status__in=statuses_to_check,
        updated_at__date__lte=cutoff,
    )

    if has_paid:
        qs = qs.exclude(status=paid_value)

    suspended = 0
    for inv in qs:
        tenant = inv.tenant

        # tenant.status chuẩn mới
        if hasattr(Tenant, "Status"):
            if tenant.status == Tenant.Status.SUSPENDED:
                continue
            tenant.status = Tenant.Status.SUSPENDED
        elif hasattr(Tenant, "STATUS_SUSPENDED"):
            if tenant.status == Tenant.STATUS_SUSPENDED:
                continue
            tenant.status = Tenant.STATUS_SUSPENDED
        else:
            # fallback: nếu tenant chưa có status field thì skip (nhưng bạn đã migrate status rồi)
            continue

        if hasattr(tenant, "suspended_at"):
            tenant.suspended_at = timezone.now()

        fields = ["status"]
        if hasattr(tenant, "suspended_at"):
            fields.append("suspended_at")
        tenant.save(update_fields=fields)

        log_change(
            action="tenant_suspended",
            model="tenants.Tenant",
            object_id=str(tenant.id),
            tenant_id=tenant.id,
            meta={
                "invoice_id": inv.id,
                "year": inv.year,
                "month": inv.month,
                "total_amount": inv.total_amount,
                "grace_days": grace_days,
            },
        )

        suspended += 1

    return suspended