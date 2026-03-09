from decimal import Decimal

from apps.contracts.models import ContractPayment
from apps.finance_ledger.models import LedgerEntry
from apps.contracts.models import ContractBookingItem

def record_payment_revenue(payment: ContractPayment):

    if payment.total_amount <= 0:
        return

    LedgerEntry.objects_all.create(
        tenant_id=payment.tenant_id,
        contract_id=payment.contract_id,
        entry_type=LedgerEntry.EntryType.REVENUE,
        amount=payment.total_amount,
        source_type="contract_payment",
        source_id=payment.id,
        description=f"Thanh toán hợp đồng {payment.contract.code}",
    )




def record_koc_expense(item: ContractBookingItem):

    if item.payout_amount <= 0:
        return

    LedgerEntry.objects_all.create(
        tenant_id=item.tenant_id,
        contract_id=item.contract_id,
        shop_id=item.shop_id,
        entry_type=LedgerEntry.EntryType.EXPENSE,
        amount=item.payout_amount,
        source_type="koc_payout",
        source_id=item.id,
        description=f"Payout KOC {item.koc_name}",
    )