"""
Domain models and schema definitions for QuickBooks Online Invoicing.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


class PaymentStatus(str, Enum):
    """Invoice payment lifecycle status."""
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    SENT = "SENT"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    VOIDED = "VOIDED"


class Address(BaseModel):
    """Postal address formatted for standard orders and QBO mapping."""
    line1: str = Field(..., description="Street address line 1")
    line2: Optional[str] = Field(default=None, description="Apartment, suite, unit")
    city: str = Field(..., description="City name")
    state: str = Field(..., description="State or province code (e.g. CA, NY)")
    postal_code: str = Field(..., description="Postal or ZIP code")
    country: str = Field(default="USA", description="Country name or ISO code")

    def to_qbo_dict(self) -> Dict[str, str]:
        """Format as QuickBooks Online PhysicalAddress."""
        qbo_addr = {
            "Line1": self.line1,
            "City": self.city,
            "CountrySubDivisionCode": self.state,
            "PostalCode": self.postal_code,
            "Country": self.country,
        }
        if self.line2:
            qbo_addr["Line2"] = self.line2
        return qbo_addr


class OrderCustomer(BaseModel):
    """Customer information associated with an incoming order."""
    name: str = Field(..., description="Full name or company contact")
    email: str = Field(..., description="Customer billing email")
    phone: Optional[str] = Field(default=None, description="Contact phone number")
    company_name: Optional[str] = Field(default=None, description="Organization or business name")
    qbo_customer_id: Optional[str] = Field(default=None, description="Existing QBO CustomerRef value")
    billing_address: Optional[Address] = None
    shipping_address: Optional[Address] = None


class OrderItem(BaseModel):
    """Line item in an incoming order."""
    item_id: Optional[str] = Field(default="1", description="Item SKU or QBO ItemRef ID")
    name: str = Field(..., description="Item or service name")
    description: Optional[str] = Field(default=None, description="Detailed item description")
    quantity: Decimal = Field(default=Decimal("1"), ge=Decimal("0.01"), description="Quantity purchased")
    unit_price: Decimal = Field(..., ge=Decimal("0.00"), description="Price per unit")
    tax_code: str = Field(default="TAX", description="Tax status: TAX or NON")
    discount_amount: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"), description="Direct line discount")

    @property
    def line_subtotal(self) -> Decimal:
        """Calculate line subtotal before line discount."""
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def net_line_total(self) -> Decimal:
        """Calculate line total minus line discount."""
        subtotal = self.line_subtotal - self.discount_amount
        return max(Decimal("0.00"), subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class OrderData(BaseModel):
    """Complete incoming order payload to be transformed into an invoice."""
    order_id: str = Field(..., description="Unique merchant order identifier")
    order_number: Optional[str] = Field(default=None, description="Human-readable invoice/order reference")
    customer: OrderCustomer = Field(..., description="Customer details")
    items: List[OrderItem] = Field(..., min_length=1, description="List of items in order")
    shipping_fee: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"), description="Shipping & handling")
    discount_total: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"), description="Global order discount")
    tax_rate_percent: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"), description="Sales tax percentage")
    currency: str = Field(default="USD", description="Three-letter ISO currency code")
    order_date: date = Field(default_factory=date.today, description="Date order placed")
    due_date: Optional[date] = Field(default=None, description="Invoice payment due date")
    customer_memo: Optional[str] = Field(default=None, description="Message shown to customer")
    private_note: Optional[str] = Field(default=None, description="Internal accounting note")

    @field_validator("order_number", mode="before")
    @classmethod
    def set_default_order_number(cls, v: Any, info: Any) -> Optional[str]:
        if not v and "order_id" in info.data:
            return f"ORD-{info.data['order_id']}"
        return v

    @property
    def computed_subtotal(self) -> Decimal:
        """Sum of all line items subtotal."""
        return sum((item.net_line_total for item in self.items), Decimal("0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def taxable_subtotal(self) -> Decimal:
        """Subtotal of items marked with TAX."""
        return sum(
            (item.net_line_total for item in self.items if item.tax_code.upper() == "TAX"),
            Decimal("0.00")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def computed_tax(self) -> Decimal:
        """Calculated tax amount based on taxable items."""
        if self.tax_rate_percent <= Decimal("0"):
            return Decimal("0.00")
        tax = (self.taxable_subtotal * (self.tax_rate_percent / Decimal("100.00")))
        return tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def computed_total(self) -> Decimal:
        """Final computed invoice total amount."""
        sub = self.computed_subtotal
        disc = self.discount_total
        tax = self.computed_tax
        ship = self.shipping_fee
        total = sub - disc + tax + ship
        return max(Decimal("0.00"), total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ============================================================================
# QuickBooks Online Accounting API v3 Representations
# ============================================================================

class QBOReference(BaseModel):
    """Reference object (CustomerRef, ItemRef, etc.) in QBO JSON."""
    value: str
    name: Optional[str] = None


class QBOSalesItemLineDetail(BaseModel):
    """SalesItemLineDetail node in QBO invoice."""
    ItemRef: QBOReference
    UnitPrice: Decimal
    Qty: Decimal
    TaxCodeRef: Optional[QBOReference] = None


class QBOLine(BaseModel):
    """Line item in QuickBooks Online Invoice."""
    Amount: Decimal
    DetailType: str = "SalesItemLineDetail"
    Description: Optional[str] = None
    SalesItemLineDetail: Optional[QBOSalesItemLineDetail] = None


class QBOInvoicePayload(BaseModel):
    """QuickBooks Online Accounting API v3 Invoice creation request body."""
    DocNumber: Optional[str] = None
    TxnDate: str
    DueDate: Optional[str] = None
    CustomerRef: QBOReference
    BillAddr: Optional[Dict[str, str]] = None
    ShipAddr: Optional[Dict[str, str]] = None
    Line: List[Dict[str, Any]]
    CustomerMemo: Optional[Dict[str, str]] = None
    PrivateNote: Optional[str] = None
    TotalAmt: Optional[Decimal] = None
    CurrencyRef: Optional[QBOReference] = None


# ============================================================================
# Local Storage Ledger Records
# ============================================================================

class InvoiceRecord(BaseModel):
    """Persistent database representation of a tracked invoice."""
    id: Optional[int] = None
    qbo_invoice_id: str
    order_id: str
    doc_number: str
    customer_name: str
    customer_email: str
    txn_date: str
    due_date: Optional[str] = None
    total_amount: Decimal
    balance_due: Decimal
    payment_status: PaymentStatus
    currency: str = "USD"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_payload: Optional[str] = None
    raw_response: Optional[str] = None


class PaymentRecord(BaseModel):
    """Persistent database record for payment received against an invoice."""
    id: Optional[int] = None
    qbo_payment_id: str
    qbo_invoice_id: str
    amount: Decimal
    payment_method: Optional[str] = "CreditCard"
    txn_date: str
    reference_num: Optional[str] = None
    currency: str = "USD"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_response: Optional[str] = None


class SyncLogEntry(BaseModel):
    """Audit log entry for accounting sync events."""
    id: Optional[int] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str
    entity_id: str
    status: str
    message: str
    details: Optional[Dict[str, Any]] = None


class FinancialMetrics(BaseModel):
    """Summary financial KPIs for dashboard & reporting."""
    total_invoices: int = 0
    total_invoiced_amount: Decimal = Decimal("0.00")
    total_collected_amount: Decimal = Decimal("0.00")
    total_outstanding_balance: Decimal = Decimal("0.00")
    paid_invoices_count: int = 0
    partial_invoices_count: int = 0
    pending_invoices_count: int = 0
    overdue_invoices_count: int = 0


class AgingBucket(str, Enum):
    """Aging bracket categorization for accounts receivable."""
    CURRENT = "Current"
    DAYS_1_30 = "1-30 Days"
    DAYS_31_60 = "31-60 Days"
    DAYS_61_90 = "61-90 Days"
    DAYS_OVER_90 = "90+ Days"


class DunningLevel(int, Enum):
    """Escalation severity level for overdue notices."""
    FRIENDLY = 1        # 1-14 days overdue
    URGENT = 2          # 15-30 days overdue
    FINAL_DEMAND = 3    # 31-60 days overdue
    COLLECTIONS = 4     # 61+ days overdue


class AgingBucketInvoice(BaseModel):
    """Invoice representation in an accounts receivable aging report."""
    invoice_id: str
    doc_number: str
    customer_name: str
    customer_email: Optional[str] = None
    due_date: str
    days_overdue: int
    balance_due: Decimal
    bucket: AgingBucket


class AgingScheduleReport(BaseModel):
    """Comprehensive accounts receivable aging schedule."""
    as_of_date: str
    current_amount: Decimal = Decimal("0.00")
    days_1_30_amount: Decimal = Decimal("0.00")
    days_31_60_amount: Decimal = Decimal("0.00")
    days_61_90_amount: Decimal = Decimal("0.00")
    days_over_90_amount: Decimal = Decimal("0.00")
    total_receivables: Decimal = Decimal("0.00")
    invoices: List[AgingBucketInvoice] = Field(default_factory=list)


class DunningNoticeRecord(BaseModel):
    """Persistent audit record of a dunning escalation notice."""
    id: Optional[int] = None
    invoice_id: str
    doc_number: str
    customer_name: str
    customer_email: Optional[str] = None
    escalation_level: int
    level_name: str
    days_overdue: int
    balance_due: Decimal
    subject: str
    sent_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "SENT"
    body_preview: Optional[str] = None


class DunningBatchResult(BaseModel):
    """Result summary of a batch dunning run."""
    evaluated_count: int = 0
    notices_sent_count: int = 0
    skipped_cooldown_count: int = 0
    current_count: int = 0
    notices: List[DunningNoticeRecord] = Field(default_factory=list)

