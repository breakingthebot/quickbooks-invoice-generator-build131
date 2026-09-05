"""
Integration tests for FastAPI REST API, Webhooks & Web Dashboard.
"""

import json
from decimal import Decimal
import pytest
from starlette.testclient import TestClient

from qb_invoicing.api import create_app
from qb_invoicing.models import InvoiceRecord, PaymentStatus
from qb_invoicing.webhooks import generate_qbo_webhook_signature


@pytest.fixture
def api_client(mock_settings, ledger, qbo_client, transformer, sample_order):
    ledger.save_order(sample_order)
    qbo_payload = transformer.transform_to_qbo_invoice(sample_order, doc_number="INV-API-TEST")
    created_qbo = qbo_client.create_invoice(qbo_payload)
    qbo_id = str(created_qbo["Id"])

    ledger.save_invoice(
        InvoiceRecord(
            qbo_invoice_id=qbo_id,
            order_id=sample_order.order_id,
            doc_number="INV-API-TEST",
            customer_name="API Customer",
            customer_email="api@example.com",
            txn_date=qbo_payload.TxnDate,
            due_date=qbo_payload.DueDate,
            total_amount=Decimal(str(created_qbo["TotalAmt"])),
            balance_due=Decimal(str(created_qbo["Balance"])),
            payment_status=PaymentStatus.PENDING,
        )
    )
    app = create_app(mock_settings)
    return TestClient(app)


def test_api_get_metrics(api_client):
    res = api_client.get("/api/metrics")
    assert res.status_code == 200
    data = res.json()
    assert data["total_invoices"] >= 1
    assert float(data["total_invoiced_amount"]) >= 400.0


def test_api_list_invoices(api_client):
    res = api_client.get("/api/invoices")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    assert data[0]["doc_number"] == "INV-API-TEST"


def test_api_get_invoice_detail(api_client):
    res = api_client.get("/api/invoices/INV-API-TEST")
    assert res.status_code == 200
    data = res.json()
    assert data["invoice"]["doc_number"] == "INV-API-TEST"
    assert "payments" in data


def test_api_generate_order_invoice(api_client):
    order_payload = {
        "order_id": "REST-ORDER-99",
        "customer": {"name": "REST Client", "email": "rest@client.io"},
        "items": [
            {"name": "API Service License", "quantity": 1, "unit_price": 750.00, "tax_code": "NON"}
        ],
    }
    res = api_client.post("/api/orders/generate", json=order_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["qbo_invoice_id"] is not None
    assert data["order_id"] == "REST-ORDER-99"
    assert data["total_amount"] == 750.0
    assert data["payment_status"] == "PENDING"


def test_api_record_payment(api_client):
    res = api_client.post(
        "/api/invoices/INV-API-TEST/payment",
        json={"amount": 150.00, "payment_method": "CreditCard", "reference_num": "REF-REST-1"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert data["payment"]["amount"] == 150.0
    assert data["invoice"]["balance_due"] == 850.0
    assert data["invoice"]["payment_status"] == "PARTIAL"


def test_api_webhook_unauthorized_signature(api_client):
    res = api_client.post(
        "/api/webhooks/quickbooks",
        json={"eventNotifications": []},
        headers={"intuit-signature": "bad_signature"},
    )
    assert res.status_code == 401
    assert "Invalid intuit-signature" in res.json()["detail"]


def test_api_webhook_valid_signature(api_client, mock_settings):
    payload = {
        "eventNotifications": [
            {
                "realmId": mock_settings.realm_id,
                "dataChangeEvent": {
                    "entities": [
                        {
                            "name": "Invoice",
                            "id": "1001",
                            "operation": "Update",
                            "lastUpdated": "2026-09-05T15:00:00Z",
                        }
                    ]
                },
            }
        ]
    }
    payload_bytes = json.dumps(payload).encode("utf-8")
    sig = generate_qbo_webhook_signature(payload_bytes, mock_settings.webhook_verifier_token)

    res = api_client.post(
        "/api/webhooks/quickbooks",
        content=payload_bytes,
        headers={"intuit-signature": sig, "Content-Type": "application/json"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "SUCCESS"


def test_api_web_dashboard(api_client):
    res = api_client.get("/")
    assert res.status_code == 200
    assert "QuickBooks Online Invoicing Platform" in res.text
    assert "INV-API-TEST" in res.text
