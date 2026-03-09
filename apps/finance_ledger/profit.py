from decimal import Decimal

from apps.finance_ledger.models import LedgerEntry


def calculate_contract_profit(contract_id, tenant_id):

    revenue = (
        LedgerEntry.objects_all
        .filter(
            tenant_id=tenant_id,
            contract_id=contract_id,
            entry_type="revenue",
        )
        .aggregate(total=models.Sum("amount"))["total"]
        or Decimal("0")
    )

    expense = (
        LedgerEntry.objects_all
        .filter(
            tenant_id=tenant_id,
            contract_id=contract_id,
            entry_type="expense",
        )
        .aggregate(total=models.Sum("amount"))["total"]
        or Decimal("0")
    )

    profit = revenue - expense

    return {
        "revenue": revenue,
        "expense": expense,
        "profit": profit,
    }