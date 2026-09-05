"""
Order to QuickBooks Online Invoice transformation engine.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from qb_invoicing.config import settings
from qb_invoicing.models import (
    Address,
    OrderCustomer,
    OrderData,
    OrderItem,
    QBOInvoicePayload,
    QBOReference,
)


class OrderTransformer:
    """Transforms standard e-commerce/ERP order payloads into QuickBooks Online Accounting API v3 Invoices."""

    def __init__(self, default_terms_days: int = 30):
        self.default_terms_days = default_terms_days

    def load_order_from_file(self, file_path: Union[str, Path]) -> OrderData:
        """Read and parse order JSON from a file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Order file not found at: {file_path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return self.parse_order(data)

    def parse_order(self, data: Union[str, Dict[str, Any]]) -> OrderData:
        """Parse order data from a dictionary or JSON string."""
        if isinstance(data, str):
            payload = json.loads(data)
        else:
            payload = data
        return OrderData(**payload)

    def transform_to_qbo_invoice(
        self,
        order: OrderData,
        qbo_customer_id: Optional[str] = None,
        doc_number: Optional[str] = None,
    ) -> QBOInvoicePayload:
        """
        Transforms validated OrderData into the official QuickBooks Online v3 Invoice format.
        
        Rules:
        - CustomerRef maps to existing qbo_customer_id, order.customer.qbo_customer_id, or customer name.
        - Lines format: each item becomes DetailType "SalesItemLineDetail" with ItemRef and TaxCodeRef.
        - Shipping is mapped as an explicit Line item with DetailType "SalesItemLineDetail" or "DescriptionOnly".
        - Discounts are added as a discount Line item if greater than 0.
        - DueDate defaults to order_date + default_terms_days unless specified.
        - BillAddr / ShipAddr mapped to QBO PhysicalAddress structure.
        """
        # Resolve Customer Reference
        cust_id = (
            qbo_customer_id
            or order.customer.qbo_customer_id
            or "1"  # Default QBO Customer ID fallback for mock/sandbox
        )
        customer_ref = QBOReference(value=str(cust_id), name=order.customer.name)

        # Resolve Dates
        txn_date_str = order.order_date.isoformat()
        if order.due_date:
            due_date_str = order.due_date.isoformat()
        else:
            calc_due = order.order_date + timedelta(days=self.default_terms_days)
            due_date_str = calc_due.isoformat()

        # Build Line Items
        qbo_lines: List[Dict[str, Any]] = []

        for idx, item in enumerate(order.items, start=1):
            line_amount = float(item.net_line_total)
            line_detail = {
                "ItemRef": {
                    "value": str(item.item_id or settings.default_item_ref),
                    "name": item.name,
                },
                "UnitPrice": float(item.unit_price),
                "Qty": float(item.quantity),
                "TaxCodeRef": {
                    "value": item.tax_code.upper() if item.tax_code.upper() in ("TAX", "NON") else "TAX"
                },
            }

            line_entry: Dict[str, Any] = {
                "LineNum": idx,
                "Description": item.description or item.name,
                "Amount": line_amount,
                "DetailType": "SalesItemLineDetail",
                "SalesItemLineDetail": line_detail,
            }
            qbo_lines.append(line_entry)

        # Add Shipping Fee Line if present
        if order.shipping_fee > Decimal("0.00"):
            idx = len(qbo_lines) + 1
            qbo_lines.append({
                "LineNum": idx,
                "Description": "Shipping & Handling Charges",
                "Amount": float(order.shipping_fee),
                "DetailType": "SalesItemLineDetail",
                "SalesItemLineDetail": {
                    "ItemRef": {"value": "SHIPPING", "name": "Shipping"},
                    "UnitPrice": float(order.shipping_fee),
                    "Qty": 1.0,
                    "TaxCodeRef": {"value": "NON"},
                },
            })

        # Add Global Discount Line if present
        if order.discount_total > Decimal("0.00"):
            idx = len(qbo_lines) + 1
            qbo_lines.append({
                "LineNum": idx,
                "Description": "Order Discount Applied",
                "Amount": float(order.discount_total),
                "DetailType": "DiscountLineDetail",
                "DiscountLineDetail": {
                    "PercentBased": False,
                    "DiscountAccountRef": {"value": "DISCOUNT", "name": "Discounts Given"},
                },
            })

        # Resolve Document Number (Invoice #)
        invoice_doc_num = doc_number or order.order_number or f"INV-{order.order_id}"

        # Resolve Addresses
        bill_addr = order.customer.billing_address.to_qbo_dict() if order.customer.billing_address else None
        ship_addr = order.customer.shipping_address.to_qbo_dict() if order.customer.shipping_address else (
            bill_addr.copy() if bill_addr else None
        )

        # Memo and Notes
        memo = {"value": order.customer_memo} if order.customer_memo else {
            "value": f"Thank you for your order {order.order_id}!"
        }
        private_note = order.private_note or f"Auto-generated from Order #{order.order_id} on {order.order_date}"

        return QBOInvoicePayload(
            DocNumber=invoice_doc_num,
            TxnDate=txn_date_str,
            DueDate=due_date_str,
            CustomerRef=customer_ref,
            BillAddr=bill_addr,
            ShipAddr=ship_addr,
            Line=qbo_lines,
            CustomerMemo=memo,
            PrivateNote=private_note,
            TotalAmt=order.computed_total,
            CurrencyRef=QBOReference(value=order.currency),
        )
