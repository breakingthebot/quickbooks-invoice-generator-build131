"""
Unit tests for PaymentStatusTracker.
"""

from decimal import Decimal
from datetime import date, timedelta
from qb_invoicing.models import InvoiceRecord, PaymentStatus
from qb_invoicing.payment_tracker import PaymentStatusTracker


def test_determine_status(tracker):
    # Zero balance = PAID
    assert tracker.determine_status(Decimal("100"), Decimal("0"), "2026-10-01") == PaymentStatus.PAID

    # Partial balance not overdue = PARTIAL
    future_date = (date.today() + timedelta(days=10)).isoformat()
    assert tracker.determine_status(Decimal("100"), Decimal("40"), future_date) == PaymentStatus.PARTIAL

    # Full balance not overdue = PENDING
    assert tracker.determine_status(Decimal("100"), Decimal("100"), future_date) == PaymentStatus.PENDING

    # Past due date = OVERDUE
    past_date = (date.today() - timedelta(days=5)).isoformat()
    assert tracker.determine_status(Decimal("100"), Decimal("100"), past_date) == PaymentStatus.OVERDUE
    assert tracker.determine_status(Decimal("100"), Decimal("40"), past_date) == PaymentStatus.OVERDUE


def test_sync_and_record_payment_workflow(tracker, qbo_client, ledger, transformer, sample_order):
    ledger.save_order(sample_order)
    payload = transformer.transform_to_qbo_invoice(sample_order)
    qbo_inv = qbo_client.create_invoice(payload)
    qbo_id = qbo_inv["Id"]

    # Initial invoice record in ledger
    inv_rec = InvoiceRecord(
        qbo_invoice_id=qbo_id,
        order_id=sample_order.order_id,
        doc_number=sample_order.order_number,
        customer_name=sample_order.customer.name,
        customer_email=sample_order.customer.email,
        txn_date=payload.TxnDate,
        due_date=payload.DueDate,
        total_amount=Decimal(str(qbo_inv["TotalAmt"])),
        balance_due=Decimal(str(qbo_inv["Balance"])),
        payment_status=PaymentStatus.PENDING,
    )
    ledger.save_invoice(inv_rec)

    # 1. Record partial payment of $300
    tracker.record_manual_payment(
        qbo_invoice_id=qbo_id,
        amount=Decimal("300.00"),
        payment_method="CreditCard",
        reference_num="REF-1",
    )

    synced = ledger.get_invoice_by_id(qbo_id)
    assert synced.payment_status == PaymentStatus.PARTIAL
    assert synced.balance_due == Decimal(str(round(float(inv_rec.total_amount) - 300.0, 2)))

    # 2. Record remaining payment to make it PAID
    remaining = synced.balance_due
    tracker.record_manual_payment(
        qbo_invoice_id=qbo_id,
        amount=remaining,
        payment_method="BankTransfer",
        reference_num="REF-2",
    )

    final_sync = ledger.get_invoice_by_id(qbo_id)
    assert final_sync.payment_status == PaymentStatus.PAID
    assert final_sync.balance_due == Decimal("0.00")
