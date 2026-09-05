"""
Unit tests for domain models and calculations.
"""

from decimal import Decimal
from datetime import date
import pytest
from pydantic import ValidationError

from qb_invoicing.models import (
    Address,
    FinancialMetrics,
    OrderCustomer,
    OrderData,
    OrderItem,
    PaymentStatus,
)


def test_address_to_qbo_dict():
    addr = Address(
        line1="100 Main St",
        line2="Suite 4B",
        city="Denver",
        state="CO",
        postal_code="80202",
        country="USA",
    )
    qbo_dict = addr.to_qbo_dict()
    assert qbo_dict["Line1"] == "100 Main St"
    assert qbo_dict["Line2"] == "Suite 4B"
    assert qbo_dict["City"] == "Denver"
    assert qbo_dict["CountrySubDivisionCode"] == "CO"
    assert qbo_dict["PostalCode"] == "80202"
    assert qbo_dict["Country"] == "USA"


def test_order_item_calculations():
    item = OrderItem(
        name="Widget Pro",
        quantity=Decimal("3"),
        unit_price=Decimal("25.50"),
        discount_amount=Decimal("5.00"),
    )
    assert item.line_subtotal == Decimal("76.50")
    assert item.net_line_total == Decimal("71.50")


def test_order_data_tax_and_total_calculations():
    order = OrderData(
        order_id="ORD-99",
        customer=OrderCustomer(name="John Doe", email="john@example.com"),
        items=[
            OrderItem(
                name="Taxable Item 1",
                quantity=Decimal("2"),
                unit_price=Decimal("100.00"),
                tax_code="TAX",
            ),
            OrderItem(
                name="Non-taxable Item 2",
                quantity=Decimal("1"),
                unit_price=Decimal("50.00"),
                tax_code="NON",
            ),
        ],
        shipping_fee=Decimal("15.00"),
        discount_total=Decimal("20.00"),
        tax_rate_percent=Decimal("10.00"),  # 10% on $200 taxable = $20
    )
    # Subtotal: 200 + 50 = 250
    assert order.computed_subtotal == Decimal("250.00")
    # Taxable: 200.00
    assert order.taxable_subtotal == Decimal("200.00")
    # Tax: 10% of 200 = 20.00
    assert order.computed_tax == Decimal("20.00")
    # Total: 250 - 20 (discount) + 20 (tax) + 15 (shipping) = 265.00
    assert order.computed_total == Decimal("265.00")


def test_order_data_validation_empty_items():
    with pytest.raises(ValidationError):
        OrderData(
            order_id="ORD-FAIL",
            customer=OrderCustomer(name="John", email="john@example.com"),
            items=[],
        )


def test_financial_metrics_defaults():
    m = FinancialMetrics()
    assert m.total_invoices == 0
    assert m.total_invoiced_amount == Decimal("0.00")
    assert m.total_collected_amount == Decimal("0.00")
    assert m.total_outstanding_balance == Decimal("0.00")
