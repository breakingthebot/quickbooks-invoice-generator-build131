"""
Unit tests for QuickBooksClient and MockQBOEngine.
"""

from decimal import Decimal
from qb_invoicing.qbo_client import QuickBooksClient


def test_mock_create_and_get_customer(qbo_client):
    customer = qbo_client.get_or_create_customer(
        name="Nova Dynamics",
        email="finance@novadynamics.com",
        company="Nova Dynamics Inc",
    )
    assert customer["Id"] is not None
    assert customer["DisplayName"] == "Nova Dynamics"

    # Re-fetch should return the same customer
    same_customer = qbo_client.get_or_create_customer(
        name="Nova Dynamics",
        email="finance@novadynamics.com",
    )
    assert same_customer["Id"] == customer["Id"]


def test_mock_create_and_get_invoice(qbo_client, transformer, sample_order):
    payload = transformer.transform_to_qbo_invoice(sample_order)
    invoice = qbo_client.create_invoice(payload)

    assert invoice["Id"] is not None
    assert invoice["DocNumber"] == "INV-2026-TEST"
    assert invoice["Balance"] == invoice["TotalAmt"]
    assert invoice["Balance"] > 0

    fetched = qbo_client.get_invoice(invoice["Id"])
    assert fetched is not None
    assert fetched["Id"] == invoice["Id"]
    assert fetched["DocNumber"] == "INV-2026-TEST"


def test_mock_record_payment(qbo_client, transformer, sample_order):
    payload = transformer.transform_to_qbo_invoice(sample_order)
    inv = qbo_client.create_invoice(payload)
    inv_id = inv["Id"]
    initial_balance = inv["Balance"]

    # Record partial payment
    pay_res = qbo_client.record_payment(
        invoice_id=inv_id,
        amount=200.0,
        payment_method="CreditCard",
        reference_num="TXN-9988",
    )
    assert pay_res["Id"] is not None
    assert pay_res["TotalAmt"] == 200.0

    # Verify balance reduced on invoice
    updated_inv = qbo_client.get_invoice(inv_id)
    assert round(updated_inv["Balance"], 2) == round(initial_balance - 200.0, 2)

    # Verify query payments
    payments = qbo_client.get_payments_for_invoice(inv_id)
    assert len(payments) == 1
    assert payments[0]["PaymentRefNum"] == "TXN-9988"
