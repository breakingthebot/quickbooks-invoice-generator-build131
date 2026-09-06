"""
Tests for Automated Dunning & Aging Schedule Engine.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from qb_invoicing.config import Settings
from qb_invoicing.dunning import (
    DunningEngine,
    generate_dunning_content,
    get_escalation_level,
)
from qb_invoicing.ledger import LedgerRepository
from qb_invoicing.models import (
    AgingBucket,
    DunningLevel,
    InvoiceRecord,
    OrderData,
    PaymentStatus,
)


@pytest.fixture
def test_db_path(tmp_path):
    return str(tmp_path / "test_dunning_ledger.db")


@pytest.fixture
def test_settings(test_db_path):
    return Settings(
        use_mock=True,
        database_path=test_db_path,
        dunning_cooldown_days=7,
        company_name="Test Corp",
        company_email="billing@test.com",
    )


@pytest.fixture
def sample_invoice():
    return InvoiceRecord(
        qbo_invoice_id="9001",
        order_id="ORD-9001",
        doc_number="INV-9001",
        customer_name="John Doe",
        customer_email="john@example.com",
        txn_date="2026-08-01",
        due_date="2026-08-15",
        total_amount=Decimal("500.00"),
        balance_due=Decimal("500.00"),
        payment_status=PaymentStatus.PENDING,
        currency="USD",
    )


def test_escalation_level_determination():
    assert get_escalation_level(0) is None
    assert get_escalation_level(-5) is None

    tier1, name1 = get_escalation_level(10)
    assert tier1 == DunningLevel.FRIENDLY
    assert "Friendly" in name1

    tier2, name2 = get_escalation_level(20)
    assert tier2 == DunningLevel.URGENT
    assert "Urgent" in name2

    tier3, name3 = get_escalation_level(45)
    assert tier3 == DunningLevel.FINAL_DEMAND
    assert "Final Demand" in name3

    tier4, name4 = get_escalation_level(75)
    assert tier4 == DunningLevel.COLLECTIONS
    assert "Collections" in name4


def test_generate_dunning_content(sample_invoice):
    subject, text, html = generate_dunning_content(
        invoice=sample_invoice,
        level=DunningLevel.FRIENDLY,
        level_name="Friendly Reminder",
        days_overdue=10,
        company_name="Test Corp",
        company_email="billing@test.com",
        company_phone="555-0100",
        portal_url="https://pay.example.com",
    )

    assert "Friendly Payment Reminder" in subject
    assert "INV-9001" in subject
    assert "10 days" in text or "10" in text
    assert "$500.00 USD" in text
    assert "<!DOCTYPE html>" in html
    assert "Pay Invoice Online" in html


def test_dunning_engine_evaluate_invoice(test_settings, sample_invoice):
    ledger = LedgerRepository(test_settings.database_path)
    engine = DunningEngine(ledger=ledger, settings=test_settings)

    # Save order and invoice
    order = OrderData(
        order_id="ORD-9001",
        customer={"name": "John Doe", "email": "john@example.com"},
        items=[{"name": "Widget", "unit_price": 500.0, "quantity": 1}],
    )
    ledger.save_order(order)
    ledger.save_invoice(sample_invoice)

    # Evaluate as of 2026-08-25 (10 days overdue -> Friendly)
    notice = engine.evaluate_invoice(
        invoice_id="9001",
        as_of_date="2026-08-25",
        force=False,
    )
    assert notice is not None
    assert notice.escalation_level == 1
    assert notice.days_overdue == 10
    assert notice.balance_due == Decimal("500.00")
    assert notice.doc_number == "INV-9001"


def test_dunning_engine_cooldown(test_settings, sample_invoice):
    ledger = LedgerRepository(test_settings.database_path)
    engine = DunningEngine(ledger=ledger, settings=test_settings)

    order = OrderData(
        order_id="ORD-9001",
        customer={"name": "John Doe", "email": "john@example.com"},
        items=[{"name": "Widget", "unit_price": 500.0, "quantity": 1}],
    )
    ledger.save_order(order)
    ledger.save_invoice(sample_invoice)

    # Run dunning cycle
    res1 = engine.run_dunning_cycle(as_of_date="2026-08-25", cooldown_days=7)
    assert res1.notices_sent_count == 1

    # Second run immediately after should skip due to cooldown
    res2 = engine.run_dunning_cycle(as_of_date="2026-08-25", cooldown_days=7, force=False)
    assert res2.notices_sent_count == 0
    assert res2.skipped_cooldown_count == 1

    # Forcing run should bypass cooldown
    res3 = engine.run_dunning_cycle(as_of_date="2026-08-25", cooldown_days=7, force=True)
    assert res3.notices_sent_count == 1


def test_aging_schedule_buckets(test_settings):
    ledger = LedgerRepository(test_settings.database_path)
    engine = DunningEngine(ledger=ledger, settings=test_settings)

    ref_date = "2026-09-01"

    # Current invoice (due 2026-09-15)
    inv_current = InvoiceRecord(
        qbo_invoice_id="101",
        order_id="ORD-101",
        doc_number="INV-101",
        customer_name="Alice",
        customer_email="alice@example.com",
        txn_date="2026-08-15",
        due_date="2026-09-15",
        total_amount=Decimal("100.00"),
        balance_due=Decimal("100.00"),
        payment_status=PaymentStatus.PENDING,
    )

    # 1-30 days overdue (due 2026-08-15 -> 17 days overdue)
    inv_1_30 = InvoiceRecord(
        qbo_invoice_id="102",
        order_id="ORD-102",
        doc_number="INV-102",
        customer_name="Bob",
        customer_email="bob@example.com",
        txn_date="2026-07-15",
        due_date="2026-08-15",
        total_amount=Decimal("200.00"),
        balance_due=Decimal("200.00"),
        payment_status=PaymentStatus.OVERDUE,
    )

    # 31-60 days overdue (due 2026-07-15 -> 48 days overdue)
    inv_31_60 = InvoiceRecord(
        qbo_invoice_id="103",
        order_id="ORD-103",
        doc_number="INV-103",
        customer_name="Charlie",
        customer_email="charlie@example.com",
        txn_date="2026-06-15",
        due_date="2026-07-15",
        total_amount=Decimal("300.00"),
        balance_due=Decimal("300.00"),
        payment_status=PaymentStatus.OVERDUE,
    )

    for o_id, cust in [("ORD-101", "Alice"), ("ORD-102", "Bob"), ("ORD-103", "Charlie")]:
        ledger.save_order(
            OrderData(
                order_id=o_id,
                customer={"name": cust, "email": f"{cust.lower()}@example.com"},
                items=[{"name": "Consulting", "unit_price": 100.0, "quantity": 1}],
            )
        )

    ledger.save_invoice(inv_current)
    ledger.save_invoice(inv_1_30)
    ledger.save_invoice(inv_31_60)

    report = engine.get_aging_schedule(as_of_date=ref_date)
    assert report.current_amount == Decimal("100.00")
    assert report.days_1_30_amount == Decimal("200.00")
    assert report.days_31_60_amount == Decimal("300.00")
    assert report.total_receivables == Decimal("600.00")
    assert len(report.invoices) == 3
