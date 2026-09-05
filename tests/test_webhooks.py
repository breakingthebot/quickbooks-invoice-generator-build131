"""
Unit tests for QuickBooks Online Webhooks & Cryptographic Signature Verification.
"""

import json
from decimal import Decimal
from datetime import datetime, timezone
import pytest

from qb_invoicing.models import InvoiceRecord, PaymentStatus
from qb_invoicing.webhooks import (
    WebhookProcessor,
    generate_qbo_webhook_signature,
    verify_qbo_webhook_signature,
)


def test_webhook_signature_verification():
    token = "secret_verifier_token_123"
    payload = b'{"test": "data", "intuit": true}'
    sig = generate_qbo_webhook_signature(payload, token)

    assert sig is not None
    assert len(sig) > 10
    # Valid verification
    assert verify_qbo_webhook_signature(payload, sig, token) is True

    # Tampered payload fails
    assert verify_qbo_webhook_signature(b'{"test": "tampered"}', sig, token) is False

    # Wrong token fails
    assert verify_qbo_webhook_signature(payload, sig, "wrong_token") is False

    # Missing signature header fails
    assert verify_qbo_webhook_signature(payload, None, token) is False


def test_webhook_processor_payment_event(tracker, qbo_client, ledger, transformer, sample_order):
    processor = WebhookProcessor(client=qbo_client, ledger=ledger, tracker=tracker)
    verifier_token = "test_verifier_token"

    # 1. Setup order and invoice
    ledger.save_order(sample_order)
    qbo_payload = transformer.transform_to_qbo_invoice(sample_order)
    qbo_inv = qbo_client.create_invoice(qbo_payload)
    qbo_id = str(qbo_inv["Id"])

    ledger.save_invoice(
        InvoiceRecord(
            qbo_invoice_id=qbo_id,
            order_id=sample_order.order_id,
            doc_number=sample_order.order_number,
            customer_name=sample_order.customer.name,
            customer_email=sample_order.customer.email,
            txn_date=qbo_payload.TxnDate,
            due_date=qbo_payload.DueDate,
            total_amount=Decimal(str(qbo_inv["TotalAmt"])),
            balance_due=Decimal(str(qbo_inv["Balance"])),
            payment_status=PaymentStatus.PENDING,
        )
    )

    # 2. Record payment in QBO mock engine directly (as if user paid via Intuit invoice payment link)
    payment_record = qbo_client.record_payment(
        invoice_id=qbo_id,
        amount=250.0,
        payment_method="CreditCard",
        reference_num="INTUIT-PAY-001",
    )
    pay_id = str(payment_record["Id"])

    # 3. Simulate incoming Intuit webhook notification
    webhook_body = {
        "eventNotifications": [
            {
                "realmId": "9341452019482710",
                "dataChangeEvent": {
                    "entities": [
                        {
                            "name": "Payment",
                            "id": pay_id,
                            "operation": "Create",
                            "lastUpdated": datetime.now(timezone.utc).isoformat(),
                        }
                    ]
                },
            }
        ]
    }
    raw_bytes = json.dumps(webhook_body).encode("utf-8")
    sig = generate_qbo_webhook_signature(raw_bytes, verifier_token)

    res = processor.process_payload(raw_bytes, sig, verifier_token)
    assert res["status"] == "SUCCESS"
    assert res["events_processed"] == 1

    # 4. Verify local ledger was updated automatically!
    updated_inv = ledger.get_invoice_by_id(qbo_id)
    assert updated_inv.payment_status == PaymentStatus.PARTIAL
    assert updated_inv.balance_due == Decimal(str(round(float(qbo_inv["TotalAmt"]) - 250.0, 2)))


def test_webhook_processor_idempotency(tracker, qbo_client, ledger, transformer, sample_order):
    processor = WebhookProcessor(client=qbo_client, ledger=ledger, tracker=tracker)
    verifier_token = "test_token"

    timestamp = "2026-09-05T12:00:00Z"
    webhook_body = {
        "eventNotifications": [
            {
                "realmId": "12345",
                "dataChangeEvent": {
                    "entities": [
                        {
                            "name": "Invoice",
                            "id": "9999",
                            "operation": "Update",
                            "lastUpdated": timestamp,
                        }
                    ]
                },
            }
        ]
    }
    raw_bytes = json.dumps(webhook_body).encode("utf-8")
    sig = generate_qbo_webhook_signature(raw_bytes, verifier_token)

    # First attempt: processed
    res1 = processor.process_payload(raw_bytes, sig, verifier_token)
    assert res1["details"][0]["status"] == "PROCESSED"

    # Second attempt (replay): skipped duplicate
    res2 = processor.process_payload(raw_bytes, sig, verifier_token)
    assert res2["details"][0]["status"] == "SKIPPED_DUPLICATE"


def test_webhook_processor_void_invoice(tracker, qbo_client, ledger, transformer, sample_order):
    processor = WebhookProcessor(client=qbo_client, ledger=ledger, tracker=tracker)
    verifier_token = "test_token"

    ledger.save_order(sample_order)
    ledger.save_invoice(
        InvoiceRecord(
            qbo_invoice_id="9988",
            order_id=sample_order.order_id,
            doc_number="INV-VOID-TEST",
            customer_name="Test Customer",
            customer_email="test@example.com",
            txn_date="2026-09-01",
            total_amount=Decimal("500.00"),
            balance_due=Decimal("500.00"),
            payment_status=PaymentStatus.PENDING,
        )
    )

    webhook_body = {
        "eventNotifications": [
            {
                "realmId": "12345",
                "dataChangeEvent": {
                    "entities": [
                        {
                            "name": "Invoice",
                            "id": "9988",
                            "operation": "Void",
                            "lastUpdated": datetime.now(timezone.utc).isoformat(),
                        }
                    ]
                },
            }
        ]
    }
    raw_bytes = json.dumps(webhook_body).encode("utf-8")
    sig = generate_qbo_webhook_signature(raw_bytes, verifier_token)

    res = processor.process_payload(raw_bytes, sig, verifier_token)
    assert res["status"] == "SUCCESS"

    voided = ledger.get_invoice_by_id("9988")
    assert voided.payment_status == PaymentStatus.VOIDED
    assert voided.balance_due == Decimal("0.00")
