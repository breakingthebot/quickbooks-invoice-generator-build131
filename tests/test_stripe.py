"""
Unit and integration tests for Stripe Multi-Gateway Checkout & Auto-Settlement Engine.
Tests session generation, HMAC-SHA256 signature verification, webhook processing,
idempotency, REST API endpoints, hosted portal HTML, and CLI commands.
"""

import json
import time
from decimal import Decimal
import pytest
from click.testing import CliRunner
from starlette.testclient import TestClient

from qb_invoicing.api import create_app
from qb_invoicing.cli import cli
from qb_invoicing.models import InvoiceRecord, PaymentStatus
from qb_invoicing.stripe_engine import StripeCheckoutEngine


@pytest.fixture
def stripe_engine():
    return StripeCheckoutEngine(
        api_key="sk_test_mock_12345",
        webhook_secret="whsec_test_secret_abc123",
        use_mock=True,
    )


@pytest.fixture
def sample_invoice_record(sample_order):
    return InvoiceRecord(
        qbo_invoice_id="9001",
        order_id=sample_order.order_id,
        doc_number="INV-STRIPE-001",
        customer_name="Stripe Tester",
        customer_email="stripe@example.com",
        txn_date="2026-09-01",
        due_date="2026-09-30",
        total_amount=Decimal("450.00"),
        balance_due=Decimal("450.00"),
        payment_status=PaymentStatus.PENDING,
        currency="USD",
    )


# ============================================================================
# 1. Stripe Engine Unit Tests: Sessions & Cryptography
# ============================================================================

def test_stripe_checkout_session_creation(stripe_engine, sample_invoice_record):
    session = stripe_engine.create_checkout_session(sample_invoice_record)
    assert session.session_id.startswith("cs_test_")
    assert session.qbo_invoice_id == "9001"
    assert session.doc_number == "INV-STRIPE-001"
    assert session.amount_total == Decimal("450.00")
    assert session.currency == "usd"
    assert session.payment_status == "unpaid"
    assert f"/pay/checkout/{session.session_id}" in session.checkout_url
    assert f"/pay/success/9001" in session.success_url

    retrieved = stripe_engine.get_checkout_session(session.session_id)
    assert retrieved is not None
    assert retrieved.session_id == session.session_id


def test_stripe_signature_verification_valid(stripe_engine):
    payload = b'{"id":"evt_123","type":"checkout.session.completed"}'
    sig_header = stripe_engine.generate_signed_webhook_header(payload)
    
    assert stripe_engine.verify_webhook_signature(payload, sig_header) is True


def test_stripe_signature_verification_invalid_secret(stripe_engine):
    payload = b'{"id":"evt_123","type":"checkout.session.completed"}'
    # Generated with a different secret
    sig_header = stripe_engine.generate_signed_webhook_header(payload, secret="whsec_wrong_key_999")
    
    assert stripe_engine.verify_webhook_signature(payload, sig_header) is False


def test_stripe_signature_verification_expired_timestamp(stripe_engine):
    payload = b'{"id":"evt_123","type":"checkout.session.completed"}'
    # Timestamp 1000 seconds in past
    old_ts = int(time.time()) - 1000
    sig_header = stripe_engine.generate_signed_webhook_header(payload, timestamp=old_ts)
    
    # Within 300 seconds tolerance, this should fail
    assert stripe_engine.verify_webhook_signature(payload, sig_header, tolerance_seconds=300) is False


def test_stripe_signature_verification_corrupted_payload(stripe_engine):
    payload_original = b'{"id":"evt_123","amount":100}'
    payload_tampered = b'{"id":"evt_123","amount":999}'
    sig_header = stripe_engine.generate_signed_webhook_header(payload_original)
    
    assert stripe_engine.verify_webhook_signature(payload_tampered, sig_header) is False


def test_stripe_signature_malformed_header(stripe_engine):
    payload = b'{"id":"evt_123"}'
    assert stripe_engine.verify_webhook_signature(payload, "invalid_header_format") is False
    assert stripe_engine.verify_webhook_signature(payload, "") is False
    assert stripe_engine.verify_webhook_signature(b"", "t=123,v1=abc") is False


# ============================================================================
# 2. Webhook Event Processing & Auto-Reconciliation Tests
# ============================================================================

def test_stripe_webhook_process_card_payment(stripe_engine, ledger, tracker, qbo_client, sample_order, sample_invoice_record):
    ledger.save_order(sample_order)
    ledger.save_invoice(sample_invoice_record)

    event_payload = {
        "id": "evt_card_test_01",
        "object": "event",
        "type": "checkout.session.completed",
        "created": int(time.time()),
        "data": {
            "object": {
                "id": "cs_test_card_1",
                "amount_total": 45000,  # 450.00 USD in cents
                "currency": "usd",
                "payment_method_types": ["card"],
                "metadata": {
                    "qbo_invoice_id": "9001",
                    "doc_number": "INV-STRIPE-001",
                },
            }
        },
    }

    result = stripe_engine.process_webhook_event(event_payload, ledger, tracker, qbo_client)
    assert result.success is True
    assert result.invoice_id == "9001"
    assert result.amount_paid == Decimal("450.00")
    assert result.new_balance == Decimal("0.00")
    assert result.payment_status == PaymentStatus.PAID

    # Verify ledger updated
    updated = ledger.get_invoice_by_id("9001")
    assert updated.balance_due == Decimal("0.00")
    assert updated.payment_status == PaymentStatus.PAID

    # Verify webhook event table
    assert ledger.is_webhook_event_processed("evt_card_test_01") is True


def test_stripe_webhook_process_ach_partial_payment(stripe_engine, ledger, tracker, qbo_client, sample_order):
    ledger.save_order(sample_order)
    inv = InvoiceRecord(
        qbo_invoice_id="9002",
        order_id=sample_order.order_id,
        doc_number="INV-ACH-001",
        customer_name="ACH Corp",
        customer_email="ach@example.com",
        txn_date="2026-09-01",
        due_date="2026-09-30",
        total_amount=Decimal("1000.00"),
        balance_due=Decimal("1000.00"),
        payment_status=PaymentStatus.PENDING,
        currency="USD",
    )
    ledger.save_invoice(inv)

    event_payload = {
        "id": "evt_ach_test_01",
        "object": "event",
        "type": "checkout.session.completed",
        "created": int(time.time()),
        "data": {
            "object": {
                "id": "cs_test_ach_1",
                "amount_total": 40000,  # $400.00
                "currency": "usd",
                "payment_method_types": ["us_bank_account"],
                "metadata": {
                    "qbo_invoice_id": "9002",
                    "doc_number": "INV-ACH-001",
                },
            }
        },
    }

    result = stripe_engine.process_webhook_event(event_payload, ledger, tracker, qbo_client)
    assert result.success is True
    assert result.amount_paid == Decimal("400.00")
    assert result.new_balance == Decimal("600.00")
    assert result.payment_status == PaymentStatus.PARTIAL

    payments = ledger.get_payments_for_invoice("9002")
    assert len(payments) == 1
    assert payments[0].payment_method == "ACH"


def test_stripe_webhook_idempotency(stripe_engine, ledger, tracker, qbo_client, sample_order, sample_invoice_record):
    ledger.save_order(sample_order)
    sample_invoice_record.qbo_invoice_id = "9003"
    sample_invoice_record.doc_number = "INV-STRIPE-IDEMP"
    ledger.save_invoice(sample_invoice_record)

    event_payload = {
        "id": "evt_idempotent_test_99",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_idemp_1",
                "amount_total": 45000,
                "payment_method_types": ["card"],
                "metadata": {"qbo_invoice_id": "9003"},
            }
        },
    }

    # First run
    res1 = stripe_engine.process_webhook_event(event_payload, ledger, tracker, qbo_client)
    assert res1.success is True
    assert res1.new_balance == Decimal("0.00")

    # Duplicate run with same event_id
    res2 = stripe_engine.process_webhook_event(event_payload, ledger, tracker, qbo_client)
    assert res2.success is True
    assert "Idempotent skip" in res2.message

    # Ensure duplicate payment record was NOT created
    payments = ledger.get_payments_for_invoice("9003")
    assert len(payments) == 1


def test_stripe_webhook_non_accounting_event(stripe_engine, ledger, tracker, qbo_client):
    event = {
        "id": "evt_customer_created_1",
        "type": "customer.created",
        "data": {"object": {"id": "cus_123"}},
    }
    result = stripe_engine.process_webhook_event(event, ledger, tracker, qbo_client)
    assert result.success is True
    assert "acknowledged but requires no accounting action" in result.message


# ============================================================================
# 3. REST API Endpoint Integration Tests
# ============================================================================

@pytest.fixture
def stripe_api_client(mock_settings, ledger, sample_order, sample_invoice_record):
    ledger.save_order(sample_order)
    ledger.save_invoice(sample_invoice_record)
    app = create_app(mock_settings)
    return TestClient(app)


def test_api_stripe_checkout_session_endpoint(stripe_api_client):
    res = stripe_api_client.post("/api/invoices/INV-STRIPE-001/checkout-session")
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"].startswith("cs_test_")
    assert data["doc_number"] == "INV-STRIPE-001"
    assert "/pay/checkout/" in data["checkout_url"]


def test_api_stripe_webhook_signature_handling(stripe_api_client, mock_settings):
    payload = {
        "id": "evt_api_test_01",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_api_test",
                "amount_total": 45000,
                "payment_method_types": ["card"],
                "metadata": {"qbo_invoice_id": "9001", "doc_number": "INV-STRIPE-001"},
            }
        },
    }
    payload_bytes = json.dumps(payload).encode("utf-8")

    # 1. Missing signature header -> 400
    res_missing = stripe_api_client.post("/api/webhooks/stripe", content=payload_bytes)
    assert res_missing.status_code == 400

    # 2. Invalid signature header -> 401
    res_invalid = stripe_api_client.post(
        "/api/webhooks/stripe",
        content=payload_bytes,
        headers={"stripe-signature": "t=123,v1=bad_signature_hash"},
    )
    assert res_invalid.status_code == 401

    # 3. Valid signature header -> 200
    engine = StripeCheckoutEngine(webhook_secret=mock_settings.stripe_webhook_secret)
    valid_sig = engine.generate_signed_webhook_header(payload_bytes)
    res_valid = stripe_api_client.post(
        "/api/webhooks/stripe",
        content=payload_bytes,
        headers={"stripe-signature": valid_sig},
    )
    assert res_valid.status_code == 200
    assert res_valid.json()["success"] is True


def test_api_stripe_simulate_endpoint(stripe_api_client):
    payload = {"invoice_id": "INV-STRIPE-001", "amount": 450.0, "payment_method": "CreditCard"}
    res = stripe_api_client.post("/api/pay/simulate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["payment_status"] == "PAID"
    assert float(data["new_balance"]) == 0.0


def test_api_hosted_payment_portal_pages(stripe_api_client):
    # Customer Payment Portal
    res_portal = stripe_api_client.get("/pay/INV-STRIPE-001")
    assert res_portal.status_code == 200
    assert "Customer Payment Portal" in res_portal.text
    assert "INV-STRIPE-001" in res_portal.text
    assert "Proceed to Stripe Checkout" in res_portal.text

    # Mock Checkout Sandbox page
    cs_res = stripe_api_client.post("/api/invoices/INV-STRIPE-001/checkout-session")
    session_id = cs_res.json()["session_id"]

    res_checkout = stripe_api_client.get(f"/pay/checkout/{session_id}")
    assert res_checkout.status_code == 200
    assert "STRIPE TESTMODE SANDBOX" in res_checkout.text
    assert "INV-STRIPE-001" in res_checkout.text

    # Success Page
    res_success = stripe_api_client.get("/pay/success/9001?amount=450.00")
    assert res_success.status_code == 200
    assert "Payment Successful!" in res_success.text
    assert "$450.00" in res_success.text

    # 404 for unknown invoice
    res_404 = stripe_api_client.get("/pay/NONEXISTENT-999")
    assert res_404.status_code == 404
    assert "Invoice Not Found" in res_404.text


# ============================================================================
# 4. CLI Command Tests
# ============================================================================

def test_cli_checkout_command(tmp_path, monkeypatch):
    test_db = tmp_path / "cli_stripe_test.db"
    monkeypatch.setenv("DATABASE_PATH", str(test_db))

    runner = CliRunner()
    # Init DB and generate sample
    runner.invoke(cli, ["init-db"])
    runner.invoke(cli, ["generate", "--order", "samples/sample_order_ecommerce.json"])

    # Run checkout command
    res = runner.invoke(cli, ["checkout", "--invoice", "1001"])
    assert res.exit_code == 0
    assert "Created Stripe Checkout Session" in res.output
    assert "cs_test_" in res.output
    assert "/pay/checkout/" in res.output


def test_cli_simulate_stripe_payment_command(tmp_path, monkeypatch):
    test_db = tmp_path / "cli_stripe_test2.db"
    monkeypatch.setenv("DATABASE_PATH", str(test_db))

    runner = CliRunner()
    runner.invoke(cli, ["init-db"])
    runner.invoke(cli, ["generate", "--order", "samples/sample_order_ecommerce.json"])

    # Simulate card payment
    res = runner.invoke(cli, ["simulate-stripe-payment", "--invoice", "1001", "--method", "card"])
    assert res.exit_code == 0
    assert "Stripe Payment Auto-Settled Successfully" in res.output
    assert "PAID" in res.output
    assert "Remaining Balance" in res.output
