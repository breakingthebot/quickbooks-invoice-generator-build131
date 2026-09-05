"""
Test fixtures and configuration.
"""

import pytest
from decimal import Decimal
from datetime import date
from qb_invoicing.config import Settings
from qb_invoicing.ledger import LedgerRepository
from qb_invoicing.models import Address, OrderCustomer, OrderData, OrderItem
from qb_invoicing.payment_tracker import PaymentStatusTracker
from qb_invoicing.qbo_client import QuickBooksClient
from qb_invoicing.transformer import OrderTransformer


@pytest.fixture
def mock_settings(tmp_path):
    db_file = tmp_path / "test_ledger.db"
    exports_dir = tmp_path / "exports"
    return Settings(
        use_mock=True,
        environment="sandbox",
        realm_id="9341452019482710",
        database_path=str(db_file),
        exports_dir=str(exports_dir),
    )


@pytest.fixture
def ledger(mock_settings):
    return LedgerRepository(db_path=mock_settings.database_path)


@pytest.fixture
def qbo_client(mock_settings):
    return QuickBooksClient(cfg=mock_settings)


@pytest.fixture
def tracker(qbo_client, ledger):
    return PaymentStatusTracker(client=qbo_client, ledger=ledger)


@pytest.fixture
def transformer():
    return OrderTransformer(default_terms_days=30)


@pytest.fixture
def sample_order():
    return OrderData(
        order_id="TEST-1001",
        order_number="INV-2026-TEST",
        customer=OrderCustomer(
            name="Alice Walker",
            email="alice@walkerenterprises.com",
            company_name="Walker Enterprises",
            billing_address=Address(
                line1="123 Tech Blvd",
                city="Austin",
                state="TX",
                postal_code="78701",
                country="USA",
            ),
        ),
        items=[
            OrderItem(
                item_id="SKU-PRO-01",
                name="SaaS Enterprise Seat",
                description="Annual subscription seat",
                quantity=Decimal("5"),
                unit_price=Decimal("120.00"),
                tax_code="TAX",
            ),
            OrderItem(
                item_id="SKU-ONBOARD",
                name="Dedicated Onboarding Sprint",
                description="Technical setup & migration assistance",
                quantity=Decimal("1"),
                unit_price=Decimal("450.00"),
                tax_code="NON",
            ),
        ],
        shipping_fee=Decimal("0.00"),
        discount_total=Decimal("50.00"),
        tax_rate_percent=Decimal("8.25"),
        currency="USD",
        order_date=date(2026, 9, 1),
        customer_memo="Welcome to the platform!",
    )
