"""
Unit tests for OrderTransformer and QBO payload formatting.
"""

from decimal import Decimal
from datetime import date, timedelta
from qb_invoicing.transformer import OrderTransformer


def test_transform_sample_order(transformer, sample_order):
    payload = transformer.transform_to_qbo_invoice(sample_order)

    assert payload.DocNumber == "INV-2026-TEST"
    assert payload.TxnDate == "2026-09-01"
    # Default 30 days due date: 2026-09-01 + 30 days = 2026-10-01
    assert payload.DueDate == (date(2026, 9, 1) + timedelta(days=30)).isoformat()
    assert payload.CustomerRef.name == "Alice Walker"
    assert payload.BillAddr is not None
    assert payload.BillAddr["Line1"] == "123 Tech Blvd"

    # Lines check: 2 items + 1 discount line
    lines = payload.Line
    assert len(lines) == 3
    # First item
    assert lines[0]["DetailType"] == "SalesItemLineDetail"
    assert lines[0]["Amount"] == 600.0  # 5 * 120
    # Second item
    assert lines[1]["DetailType"] == "SalesItemLineDetail"
    assert lines[1]["Amount"] == 450.0  # 1 * 450
    # Discount line
    assert lines[2]["DetailType"] == "DiscountLineDetail"
    assert lines[2]["Amount"] == 50.0


def test_transform_with_shipping(transformer, sample_order):
    sample_order.shipping_fee = Decimal("35.00")
    payload = transformer.transform_to_qbo_invoice(sample_order)

    shipping_lines = [line for line in payload.Line if line.get("SalesItemLineDetail", {}).get("ItemRef", {}).get("value") == "SHIPPING"]
    assert len(shipping_lines) == 1
    assert shipping_lines[0]["Amount"] == 35.0


def test_customer_id_override(transformer, sample_order):
    payload = transformer.transform_to_qbo_invoice(sample_order, qbo_customer_id="CUST-999")
    assert payload.CustomerRef.value == "CUST-999"
