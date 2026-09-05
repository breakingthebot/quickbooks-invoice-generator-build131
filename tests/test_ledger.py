"""
Unit tests for LedgerRepository and SQLite persistence.
"""

from decimal import Decimal
from datetime import datetime
from qb_invoicing.models import InvoiceRecord, PaymentRecord, PaymentStatus, SyncLogEntry


def test_ledger_save_and_retrieve_invoice(ledger, sample_order):
    ledger.save_order(sample_order)

    rec = InvoiceRecord(
        qbo_invoice_id="1001",
        order_id=sample_order.order_id,
        doc_number="INV-2026-TEST",
        customer_name=sample_order.customer.name,
        customer_email=sample_order.customer.email,
        txn_date="2026-09-01",
        due_date="2026-10-01",
        total_amount=Decimal("1000.00"),
        balance_due=Decimal("1000.00"),
        payment_status=PaymentStatus.PENDING,
    )
    saved = ledger.save_invoice(rec)
    assert saved.id is not None

    by_id = ledger.get_invoice_by_id("1001")
    assert by_id is not None
    assert by_id.doc_number == "INV-2026-TEST"
    assert by_id.total_amount == Decimal("1000.00")

    by_doc = ledger.get_invoice_by_doc_number("INV-2026-TEST")
    assert by_doc is not None
    assert by_doc.qbo_invoice_id == "1001"

    by_order = ledger.get_invoice_by_order_id(sample_order.order_id)
    assert by_order is not None


def test_ledger_update_payment_status(ledger, sample_order):
    ledger.save_order(sample_order)
    rec = InvoiceRecord(
        qbo_invoice_id="1002",
        order_id=sample_order.order_id,
        doc_number="INV-1002",
        customer_name="Test Customer",
        customer_email="test@example.com",
        txn_date="2026-09-01",
        total_amount=Decimal("500.00"),
        balance_due=Decimal("500.00"),
        payment_status=PaymentStatus.PENDING,
    )
    ledger.save_invoice(rec)

    # Update to PARTIAL
    ok = ledger.update_invoice_payment_status("1002", balance_due=Decimal("250.00"), payment_status=PaymentStatus.PARTIAL)
    assert ok is True

    updated = ledger.get_invoice_by_id("1002")
    assert updated.balance_due == Decimal("250.00")
    assert updated.payment_status == PaymentStatus.PARTIAL


def test_ledger_metrics(ledger, sample_order):
    ord1 = sample_order.model_copy(update={"order_id": "ORD-1"})
    ord2 = sample_order.model_copy(update={"order_id": "ORD-2"})
    ledger.save_order(ord1)
    ledger.save_order(ord2)

    # Invoice 1: Paid ($300 total, $0 balance)
    ledger.save_invoice(
        InvoiceRecord(
            qbo_invoice_id="M1",
            order_id="ORD-1",
            doc_number="INV-M1",
            customer_name="Cust 1",
            customer_email="c1@example.com",
            txn_date="2026-09-01",
            total_amount=Decimal("300.00"),
            balance_due=Decimal("0.00"),
            payment_status=PaymentStatus.PAID,
        )
    )

    # Invoice 2: Partial ($700 total, $200 balance)
    ledger.save_invoice(
        InvoiceRecord(
            qbo_invoice_id="M2",
            order_id="ORD-2",
            doc_number="INV-M2",
            customer_name="Cust 2",
            customer_email="c2@example.com",
            txn_date="2026-09-01",
            total_amount=Decimal("700.00"),
            balance_due=Decimal("200.00"),
            payment_status=PaymentStatus.PARTIAL,
        )
    )

    m = ledger.get_metrics()
    assert m.total_invoices == 2
    assert m.total_invoiced_amount == Decimal("1000.00")
    # Collected: (300 - 0) + (700 - 200) = 800.00
    assert m.total_collected_amount == Decimal("800.00")
    # Outstanding: 0 + 200 = 200.00
    assert m.total_outstanding_balance == Decimal("200.00")
    assert m.paid_invoices_count == 1
    assert m.partial_invoices_count == 1
