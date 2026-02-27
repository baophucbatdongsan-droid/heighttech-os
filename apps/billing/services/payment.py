from __future__ import annotations

from django.db import transaction

from apps.billing.models import Invoice
from apps.tenants.models import Tenant
from apps.core.audit import log_change


def mark_invoice_paid(invoice: Invoice) -> Invoice:
    # Nếu bạn chưa có PAID trong choices thì giữ FINAL và coi FINAL = đã thanh toán.
    # Nhưng chuẩn Level 18: có PAID/OVERDUE. Nếu bạn chưa add field thì tạm dùng FINAL.

    if hasattr(Invoice.Status, "PAID"):
        paid_value = Invoice.Status.PAID
    else:
        paid_value = Invoice.Status.FINAL  # fallback

    if invoice.status == paid_value:
        return invoice

    with transaction.atomic():
        invoice.status = paid_value
        invoice.save(update_fields=["status", "updated_at"])

        tenant = invoice.tenant
        # mở lại tenant
        if hasattr(Tenant, "Status"):
            tenant.status = Tenant.Status.ACTIVE
        elif hasattr(Tenant, "STATUS_ACTIVE"):
            tenant.status = Tenant.STATUS_ACTIVE

        if hasattr(tenant, "suspended_at"):
            tenant.suspended_at = None

        fields = ["status"]
        if hasattr(tenant, "suspended_at"):
            fields.append("suspended_at")
        tenant.save(update_fields=fields)

        log_change(
            action="invoice_paid",
            model="billing.Invoice",
            object_id=str(invoice.id),
            tenant_id=tenant.id,
            meta={
                "year": invoice.year,
                "month": invoice.month,
                "total_amount": invoice.total_amount,
            },
        )

    return invoice