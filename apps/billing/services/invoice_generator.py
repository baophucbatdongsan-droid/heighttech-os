from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from apps.tenants.models import Tenant
from apps.billing.models import Invoice
from .billing import build_invoice_preview


def prev_month_of(d: date) -> tuple[int, int]:
    if d.month == 1:
        return d.year - 1, 12
    return d.year, d.month - 1


@dataclass(frozen=True)
class InvoiceRunResult:
    year: int
    month: int
    created_or_updated: int


@transaction.atomic
def generate_monthly_invoices(target_year: int | None = None, target_month: int | None = None) -> dict:
    """
    Level 18:
    - Generate invoice draft/preview cho tất cả tenant cho THÁNG TRƯỚC (default)
    - Update_or_create nên chạy lại không sao
    """
    today = timezone.localdate()
    y, m = (target_year, target_month) if target_year and target_month else prev_month_of(today)

    tenants = Tenant.objects.filter(is_active=True)
    n = 0

    for t in tenants:
        inv = build_invoice_preview(t, y, m)

        # Level 18: khi generate invoice monthly, chuyển DRAFT -> FINAL (nếu muốn)
        # Bạn có thể để DRAFT và founder review rồi mới FINAL.
        # Mình set FINAL để production:
        if hasattr(Invoice.Status, "FINAL"):
            inv.status = Invoice.Status.FINAL
            inv.save(update_fields=["status", "updated_at"])

        n += 1

    return {"year": y, "month": m, "created_or_updated": n}