"""
Rendering engine for invoices (Plain text summary and HTML).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional
from jinja2 import Template

from qb_invoicing.models import InvoiceRecord, OrderData, PaymentStatus

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Invoice {{ invoice.doc_number }}</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 40px; color: #1f2937; background: #f9fafb; }
        .invoice-card { background: white; max-width: 800px; margin: 0 auto; padding: 40px; border-radius: 8px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
        .header { display: flex; justify-content: space-between; border-bottom: 2px solid #e5e7eb; padding-bottom: 20px; }
        .logo { font-size: 24px; font-weight: bold; color: #15803d; }
        .status-badge { display: inline-block; padding: 6px 14px; border-radius: 9999px; font-weight: 600; font-size: 13px; text-transform: uppercase; }
        .status-PAID { background: #dcfce7; color: #166534; }
        .status-PENDING { background: #fef9c3; color: #854d0e; }
        .status-PARTIAL { background: #e0e7ff; color: #3730a3; }
        .status-OVERDUE { background: #fee2e2; color: #991b1b; }
        .meta-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-top: 24px; font-size: 14px; }
        table { width: 100%; border-collapse: collapse; margin-top: 32px; }
        th { text-align: left; padding: 12px; background: #f3f4f6; font-size: 13px; text-transform: uppercase; color: #4b5563; }
        td { padding: 12px; border-bottom: 1px solid #e5e7eb; font-size: 14px; }
        .amount-col { text-align: right; }
        .totals-section { margin-top: 24px; display: flex; justify-content: flex-end; }
        .totals-table { width: 320px; }
        .totals-table td { border: none; padding: 6px 12px; }
        .total-highlight { font-size: 18px; font-weight: bold; border-top: 2px solid #1f2937 !important; }
        .footer { margin-top: 40px; text-align: center; color: #9ca3af; font-size: 12px; }
    </style>
</head>
<body>
    <div class="invoice-card">
        <div class="header">
            <div>
                <div class="logo">QuickBooks Online Invoice</div>
                <p style="margin: 4px 0 0 0; color: #6b7280; font-size: 14px;">Doc #: <strong>{{ invoice.doc_number }}</strong></p>
                <p style="margin: 2px 0 0 0; color: #6b7280; font-size: 14px;">QBO ID: {{ invoice.qbo_invoice_id }}</p>
            </div>
            <div style="text-align: right;">
                <span class="status-badge status-{{ invoice.payment_status.value }}">{{ invoice.payment_status.value }}</span>
                <p style="margin: 8px 0 0 0; font-size: 14px; color: #6b7280;">Date: {{ invoice.txn_date }}</p>
                {% if invoice.due_date %}
                <p style="margin: 2px 0 0 0; font-size: 14px; color: #6b7280;">Due: {{ invoice.due_date }}</p>
                {% endif %}
            </div>
        </div>

        <div class="meta-grid">
            <div>
                <strong style="color: #4b5563;">Billed To:</strong><br>
                <span style="font-size: 16px; font-weight: 600;">{{ invoice.customer_name }}</span><br>
                {{ invoice.customer_email }}<br>
                Order Reference: {{ invoice.order_id }}
            </div>
            <div style="text-align: right;">
                <strong style="color: #4b5563;">Balance Due:</strong><br>
                <span style="font-size: 28px; font-weight: bold; color: {% if invoice.balance_due == 0 %}#166534{% else %}#1f2937{% endif %};">
                    ${{ "%.2f"|format(invoice.balance_due) }} {{ invoice.currency }}
                </span>
            </div>
        </div>

        <div class="totals-section">
            <table class="totals-table">
                <tr>
                    <td>Total Amount:</td>
                    <td class="amount-col">${{ "%.2f"|format(invoice.total_amount) }}</td>
                </tr>
                <tr>
                    <td>Amount Paid:</td>
                    <td class="amount-col" style="color: #166534;">${{ "%.2f"|format(invoice.total_amount - invoice.balance_due) }}</td>
                </tr>
                <tr class="total-highlight">
                    <td>Remaining Balance:</td>
                    <td class="amount-col">${{ "%.2f"|format(invoice.balance_due) }}</td>
                </tr>
            </table>
        </div>

        <div class="footer">
            <p>Generated via QuickBooks Online Invoice Generator &bull; Synced with Intuit Accounting API v3</p>
        </div>
    </div>
</body>
</html>
"""


class InvoiceRenderer:
    """Renders invoice representations for human viewing."""

    @staticmethod
    def render_html(invoice: InvoiceRecord) -> str:
        """Render standalone HTML invoice view."""
        template = Template(HTML_TEMPLATE)
        return template.render(invoice=invoice)

    @staticmethod
    def render_terminal_summary(invoice: InvoiceRecord) -> str:
        """Render clean, compact plain-text summary."""
        lines = [
            "=" * 60,
            f"  INVOICE: {invoice.doc_number}  |  STATUS: {invoice.payment_status.value}",
            "=" * 60,
            f"  QuickBooks ID : {invoice.qbo_invoice_id}",
            f"  Order ID      : {invoice.order_id}",
            f"  Customer      : {invoice.customer_name} <{invoice.customer_email}>",
            f"  Txn Date      : {invoice.txn_date}",
            f"  Due Date      : {invoice.due_date or 'Upon Receipt'}",
            "-" * 60,
            f"  Total Invoiced: ${invoice.total_amount:.2f} {invoice.currency}",
            f"  Paid to Date  : ${(invoice.total_amount - invoice.balance_due):.2f} {invoice.currency}",
            f"  Balance Due   : ${invoice.balance_due:.2f} {invoice.currency}",
            "=" * 60,
        ]
        return "\n".join(lines)
