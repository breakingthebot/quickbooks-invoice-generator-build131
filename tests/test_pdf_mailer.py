"""
Unit & Integration Test Suite for Vector PDF Generation, Payment QR Codes, and Email Dispatch Engine.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from starlette.testclient import TestClient

from qb_invoicing.api import create_app
from qb_invoicing.cli import cli
from qb_invoicing.config import Settings
from qb_invoicing.ledger import LedgerRepository
from qb_invoicing.mailer import InvoiceMailer
from qb_invoicing.models import (
    Address,
    EmailDispatchRecord,
    InvoiceRecord,
    OrderCustomer,
    OrderData,
    OrderItem,
    PaymentStatus,
)
from qb_invoicing.pdf_generator import InvoicePDFGenerator, generate_payment_qr


@pytest.fixture
def mock_settings(tmp_path: Path) -> Settings:
    db_file = tmp_path / "test_pdf_mailer.db"
    exports = tmp_path / "exports"
    return Settings(
        use_mock=True,
        environment="sandbox",
        realm_id="1234567890",
        database_path=str(db_file),
        exports_dir=str(exports),
        mail_use_mock=True,
        payment_portal_url="https://pay.example.com",
    )


@pytest.fixture
def ledger(mock_settings: Settings) -> LedgerRepository:
    return LedgerRepository(mock_settings.database_path)


@pytest.fixture
def sample_invoice(ledger: LedgerRepository) -> InvoiceRecord:
    order = OrderData(
        order_id="ORD-PDF-001",
        order_number="ORD-PDF-001",
        customer=OrderCustomer(
            name="Starlight Corp",
            email="billing@starlight.io",
            company_name="Starlight Corp",
        ),
        items=[
            OrderItem(
                item_id="1",
                name="Enterprise Cloud Subscription",
                quantity=Decimal("1"),
                unit_price=Decimal("1000.00"),
            ),
            OrderItem(
                item_id="2",
                name="Express Support Fee",
                quantity=Decimal("1"),
                unit_price=Decimal("250.00"),
                tax_code="NON",
            ),
        ],
    )
    ledger.save_order(order)

    inv = InvoiceRecord(
        qbo_invoice_id="99001",
        order_id="ORD-PDF-001",
        doc_number="INV-99001",
        customer_name="Starlight Corp",
        customer_email="billing@starlight.io",
        txn_date="2026-09-01",
        due_date="2026-10-01",
        total_amount=Decimal("1250.00"),
        balance_due=Decimal("1250.00"),
        payment_status=PaymentStatus.PENDING,
        currency="USD",
        raw_payload=json.dumps({
            "Line": [
                {
                    "LineNum": 1,
                    "Description": "Enterprise Cloud Subscription",
                    "Amount": 1000.0,
                    "DetailType": "SalesItemLineDetail",
                    "SalesItemLineDetail": {
                        "ItemRef": {"value": "1", "name": "Enterprise Cloud"},
                        "UnitPrice": 1000.0,
                        "Qty": 1.0,
                        "TaxCodeRef": {"value": "TAX"},
                    },
                },
                {
                    "LineNum": 2,
                    "Description": "Express Support Fee",
                    "Amount": 250.0,
                    "DetailType": "SalesItemLineDetail",
                    "SalesItemLineDetail": {
                        "ItemRef": {"value": "2", "name": "Express Support"},
                        "UnitPrice": 250.0,
                        "Qty": 1.0,
                        "TaxCodeRef": {"value": "NON"},
                    },
                },
            ]
        }),
    )
    ledger.save_invoice(inv)
    return inv


# ============================================================================
# 1. QR Code Generation Tests
# ============================================================================

def test_generate_payment_qr_valid_png():
    """Verify QR code output starts with standard PNG magic header bytes."""
    url = "https://pay.example.com/pay/99001"
    qr_bytes = generate_payment_qr(url)
    assert isinstance(qr_bytes, bytes)
    assert len(qr_bytes) > 200
    # PNG Magic Header
    assert qr_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_generate_payment_qr_custom_box_size():
    """Verify box_size and border parameters work without error."""
    url = "https://checkout.stripe.com/pay/cs_test_12345"
    small_qr = generate_payment_qr(url, box_size=3, border=1)
    large_qr = generate_payment_qr(url, box_size=8, border=4)
    assert len(large_qr) > len(small_qr)


# ============================================================================
# 2. Vector PDF Generation Tests
# ============================================================================

def test_pdf_generation_valid_pdf_structure(mock_settings: Settings, sample_invoice: InvoiceRecord):
    """Verify vector PDF generation returns valid %PDF header and non-empty byte stream."""
    generator = InvoicePDFGenerator(mock_settings)
    pdf_bytes = generator.generate_pdf_bytes(sample_invoice)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF-")


def test_pdf_generation_with_order_data(mock_settings: Settings, ledger: LedgerRepository):
    """Verify line items and shipping details from OrderData are properly rendered into PDF."""
    order = OrderData(
        order_id="ORD-FULL-01",
        order_number="ORD-FULL-01",
        customer=OrderCustomer(
            name="Orion Aerospace",
            email="finance@orion.com",
            company_name="Orion Aerospace Inc",
            billing_address=Address(
                line1="100 Orbit Way",
                city="Cape Canaveral",
                state="FL",
                postal_code="32920",
                country="USA",
            ),
        ),
        items=[
            OrderItem(
                item_id="AERO-1",
                name="Telemetry Sensor",
                description="High-G Telemetry Unit",
                quantity=Decimal("3"),
                unit_price=Decimal("450.00"),
                tax_code="TAX",
            )
        ],
        tax_rate_percent=Decimal("8.00"),
        shipping_fee=Decimal("45.00"),
    )
    ledger.save_order(order)

    inv = InvoiceRecord(
        qbo_invoice_id="99002",
        order_id="ORD-FULL-01",
        doc_number="INV-99002",
        customer_name="Orion Aerospace",
        customer_email="finance@orion.com",
        txn_date="2026-09-02",
        due_date="2026-10-02",
        total_amount=order.computed_total,
        balance_due=order.computed_total,
        payment_status=PaymentStatus.PENDING,
    )
    ledger.save_invoice(inv)

    generator = InvoicePDFGenerator(mock_settings)
    pdf_bytes = generator.generate_pdf_bytes(inv, order=order)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 2000


def test_pdf_generation_all_payment_statuses(mock_settings: Settings, sample_invoice: InvoiceRecord):
    """Verify PDF generator styles badges across all payment status variants."""
    generator = InvoicePDFGenerator(mock_settings)
    statuses = [
        PaymentStatus.PAID,
        PaymentStatus.PARTIAL,
        PaymentStatus.OVERDUE,
        PaymentStatus.VOIDED,
        PaymentStatus.PENDING,
    ]
    for st in statuses:
        sample_invoice.payment_status = st
        sample_invoice.balance_due = Decimal("0.00") if st == PaymentStatus.PAID else Decimal("500.00")
        pdf_data = generator.generate_pdf_bytes(sample_invoice)
        assert pdf_data.startswith(b"%PDF-")


def test_pdf_save_to_filesystem(mock_settings: Settings, sample_invoice: InvoiceRecord, tmp_path: Path):
    """Verify save_pdf correctly writes binary PDF to destination directory."""
    generator = InvoicePDFGenerator(mock_settings)
    out_file = tmp_path / "custom_invoices" / "Test_Invoice.pdf"
    saved = generator.save_pdf(sample_invoice, output_path=out_file)

    assert saved.exists()
    assert saved.stat().st_size > 1000
    with open(saved, "rb") as f:
        header = f.read(5)
        assert header == b"%PDF-"


# ============================================================================
# 3. Invoice Mailer Tests
# ============================================================================

def test_mailer_simulated_dispatch(mock_settings: Settings, sample_invoice: InvoiceRecord, ledger: LedgerRepository):
    """Verify mailer mock sandbox mode dispatches simulated email and audits to SQLite ledger."""
    mock_settings.mail_use_mock = True
    mailer = InvoiceMailer(settings=mock_settings, ledger=ledger)

    dispatch = mailer.send_invoice_email(sample_invoice)
    assert dispatch.status == "SIMULATED"
    assert dispatch.has_attachment is True
    assert dispatch.recipient_email == sample_invoice.customer_email
    assert sample_invoice.doc_number in dispatch.subject
    assert dispatch.id is not None

    # Check persistence in ledger
    records = ledger.get_email_dispatches(invoice_id=sample_invoice.qbo_invoice_id)
    assert len(records) >= 1
    assert records[0].recipient_email == "billing@starlight.io"
    assert records[0].status == "SIMULATED"


def test_mailer_custom_recipient_and_subject(mock_settings: Settings, sample_invoice: InvoiceRecord, ledger: LedgerRepository):
    """Verify overriding recipient email and subject lines."""
    mailer = InvoiceMailer(settings=mock_settings, ledger=ledger)
    dispatch = mailer.send_invoice_email(
        sample_invoice,
        recipient_email="cfo@starlight.io",
        subject="Special Invoice INV-99001 Expedited",
    )
    assert dispatch.recipient_email == "cfo@starlight.io"
    assert dispatch.subject == "Special Invoice INV-99001 Expedited"


def test_mailer_missing_recipient_raises_value_error(mock_settings: Settings, ledger: LedgerRepository):
    """Verify ValueError is raised if invoice has no customer email and none is supplied."""
    order = OrderData(
        order_id="ORD-NO-EMAIL",
        order_number="ORD-NO-EMAIL",
        customer=OrderCustomer(
            name="Anonymous Client",
            email="noemail@example.com",
        ),
        items=[
            OrderItem(
                name="Consulting",
                quantity=Decimal("1"),
                unit_price=Decimal("100.00"),
            )
        ],
    )
    ledger.save_order(order)

    inv = InvoiceRecord(
        qbo_invoice_id="99003",
        order_id="ORD-NO-EMAIL",
        doc_number="INV-99003",
        customer_name="Anonymous Client",
        customer_email="",
        txn_date="2026-09-03",
        total_amount=Decimal("100.00"),
        balance_due=Decimal("100.00"),
        payment_status=PaymentStatus.PENDING,
    )
    ledger.save_invoice(inv)
    mailer = InvoiceMailer(settings=mock_settings, ledger=ledger)
    with pytest.raises(ValueError, match="No recipient email address found"):
        mailer.send_invoice_email(inv)


def test_mailer_mime_structure_and_pdf_attachment(mock_settings: Settings, sample_invoice: InvoiceRecord, ledger: LedgerRepository):
    """Verify MIME structure contains text/plain, text/html, and application/pdf attachment."""
    mailer = InvoiceMailer(settings=mock_settings, ledger=ledger)
    pdf_bytes = b"%PDF-1.4 Mock PDF Content For Testing"
    msg = mailer.build_mime_message(
        invoice=sample_invoice,
        recipient_email="test@example.com",
        subject="Invoice Test",
        text_body="Plain text message",
        html_body="<p>HTML message</p>",
        pdf_bytes=pdf_bytes,
    )

    assert msg["To"] == "test@example.com"
    assert msg["Subject"] == "Invoice Test"

    payload = msg.get_payload()
    assert len(payload) == 2  # body container + attachment
    body_container, attachment_part = payload[0], payload[1]

    # Verify attachment
    assert attachment_part.get_content_type() == "application/pdf"
    assert f"Invoice_{sample_invoice.doc_number}.pdf" in attachment_part.get("Content-Disposition")
    assert attachment_part.get_payload(decode=True) == pdf_bytes


def test_mailer_live_smtp_failure_handling(mock_settings: Settings, sample_invoice: InvoiceRecord, ledger: LedgerRepository):
    """Verify live SMTP mode records failure in ledger and raises RuntimeError on connection refused."""
    mock_settings.mail_use_mock = False
    mock_settings.smtp_host = "127.0.0.1"
    mock_settings.smtp_port = 65534  # Non-existent port

    mailer = InvoiceMailer(settings=mock_settings, ledger=ledger)
    with pytest.raises(RuntimeError, match="Failed to dispatch email via SMTP"):
        mailer.send_invoice_email(sample_invoice)

    dispatches = ledger.get_email_dispatches(invoice_id=sample_invoice.qbo_invoice_id)
    failed = [d for d in dispatches if d.status == "FAILED"]
    assert len(failed) >= 1
    assert failed[0].error_message is not None


# ============================================================================
# 4. REST API Endpoint Tests
# ============================================================================

def test_api_download_invoice_pdf(mock_settings: Settings, sample_invoice: InvoiceRecord):
    """Test GET /api/invoices/{identifier}/pdf returns streaming PDF binary."""
    app = create_app(mock_settings)
    client = TestClient(app)

    res = client.get(f"/api/invoices/{sample_invoice.doc_number}/pdf")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert f"Invoice_{sample_invoice.doc_number}.pdf" in res.headers["content-disposition"]
    assert res.content.startswith(b"%PDF-")


def test_api_download_invoice_pdf_not_found(mock_settings: Settings):
    """Test GET /api/invoices/{identifier}/pdf returns 404 for unknown invoice."""
    app = create_app(mock_settings)
    client = TestClient(app)
    res = client.get("/api/invoices/NON_EXISTENT_INV/pdf")
    assert res.status_code == 404


def test_api_get_invoice_qr(mock_settings: Settings, sample_invoice: InvoiceRecord):
    """Test GET /api/invoices/{identifier}/qr returns PNG image."""
    app = create_app(mock_settings)
    client = TestClient(app)

    res = client.get(f"/api/invoices/{sample_invoice.qbo_invoice_id}/qr")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_api_send_invoice_email(mock_settings: Settings, sample_invoice: InvoiceRecord):
    """Test POST /api/invoices/{identifier}/send-email triggers email dispatch."""
    app = create_app(mock_settings)
    client = TestClient(app)

    res = client.post(
        f"/api/invoices/{sample_invoice.doc_number}/send-email",
        json={"recipient_email": "custom_client@test.com", "subject": "Quarterly Billing Statement"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert data["dispatch"]["recipient_email"] == "custom_client@test.com"
    assert data["dispatch"]["status"] == "SIMULATED"


def test_api_get_invoice_dispatches(mock_settings: Settings, sample_invoice: InvoiceRecord):
    """Test GET /api/invoices/{identifier}/dispatches returns historical audit records."""
    app = create_app(mock_settings)
    client = TestClient(app)

    # Dispatch one email first
    client.post(f"/api/invoices/{sample_invoice.doc_number}/send-email", json={})

    res = client.get(f"/api/invoices/{sample_invoice.doc_number}/dispatches")
    assert res.status_code == 200
    records = res.json()
    assert isinstance(records, list)
    assert len(records) >= 1
    assert records[0]["invoice_id"] == sample_invoice.qbo_invoice_id


def test_api_portal_page_includes_pdf_and_qr(mock_settings: Settings, sample_invoice: InvoiceRecord):
    """Test GET /pay/{identifier} renders PDF download link and QR code image tag."""
    app = create_app(mock_settings)
    client = TestClient(app)

    res = client.get(f"/pay/{sample_invoice.qbo_invoice_id}")
    assert res.status_code == 200
    html = res.text
    assert f"/api/invoices/{sample_invoice.qbo_invoice_id}/pdf" in html
    assert f"/api/invoices/{sample_invoice.qbo_invoice_id}/qr" in html
    assert "Download PDF" in html
    assert "Scan QR Code to Pay on Mobile" in html


def test_api_dashboard_includes_pdf_and_email_actions(mock_settings: Settings, sample_invoice: InvoiceRecord):
    """Test GET / renders direct PDF and Email action triggers."""
    app = create_app(mock_settings)
    client = TestClient(app)

    res = client.get("/")
    assert res.status_code == 200
    html = res.text
    assert f"/api/invoices/{sample_invoice.qbo_invoice_id}/pdf" in html
    assert f"sendInvoiceEmail('{sample_invoice.qbo_invoice_id}')" in html


# ============================================================================
# 5. CLI Command Tests
# ============================================================================

def test_cli_export_pdf_command(mock_settings: Settings, sample_invoice: InvoiceRecord, tmp_path: Path):
    """Test qb-invoicing export-pdf --invoice INV-99001 --output custom.pdf."""
    target_pdf = tmp_path / "cli_test_invoice.pdf"
    runner = CliRunner()
    with patch("qb_invoicing.cli.get_components") as mock_comp:
        ledger = LedgerRepository(mock_settings.database_path)
        mock_comp.return_value = (MagicMock(), ledger, MagicMock(), MagicMock(), mock_settings)

        result = runner.invoke(
            cli,
            ["export-pdf", "--invoice", sample_invoice.doc_number, "--output", str(target_pdf)],
        )
        assert result.exit_code == 0
        assert "[OK] Vector PDF exported to:" in result.output
        assert target_pdf.exists()
        assert target_pdf.stat().st_size > 1000


def test_cli_send_invoice_command(mock_settings: Settings, sample_invoice: InvoiceRecord):
    """Test qb-invoicing send-invoice --invoice INV-99001 --mock."""
    runner = CliRunner()
    with patch("qb_invoicing.cli.get_components") as mock_comp:
        ledger = LedgerRepository(mock_settings.database_path)
        mock_comp.return_value = (MagicMock(), ledger, MagicMock(), MagicMock(), mock_settings)

        result = runner.invoke(
            cli,
            ["send-invoice", "--invoice", sample_invoice.doc_number, "--mock"],
        )
        assert result.exit_code == 0
        assert "[OK] Email successfully dispatched" in result.output
        assert "Invoice Dispatch Audit" in result.output


def test_cli_export_pdf_nonexistent_invoice(mock_settings: Settings):
    """Test qb-invoicing export-pdf with invalid invoice prints error message."""
    runner = CliRunner()
    with patch("qb_invoicing.cli.get_components") as mock_comp:
        ledger = LedgerRepository(mock_settings.database_path)
        mock_comp.return_value = (MagicMock(), ledger, MagicMock(), MagicMock(), mock_settings)

        result = runner.invoke(
            cli,
            ["export-pdf", "--invoice", "NON_EXISTENT_ID"],
        )
        assert result.exit_code == 0
        assert "[ERROR] Invoice 'NON_EXISTENT_ID' not found" in result.output
