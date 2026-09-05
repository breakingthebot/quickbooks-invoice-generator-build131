"""
Payment status tracker and reconciliation engine.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from qb_invoicing.ledger import LedgerRepository
from qb_invoicing.models import (
    InvoiceRecord,
    PaymentRecord,
    PaymentStatus,
    SyncLogEntry,
)
from qb_invoicing.qbo_client import QuickBooksClient


class PaymentStatusTracker:
    """Tracks and reconciles payment statuses between QuickBooks Online and the local ledger."""

    def __init__(self, client: QuickBooksClient, ledger: LedgerRepository):
        self.client = client
        self.ledger = ledger

    def determine_status(self, total_amount: Decimal, balance_due: Decimal, due_date_str: Optional[str]) -> PaymentStatus:
        """Calculate payment lifecycle status based on balance and due date."""
        if balance_due <= Decimal("0.00"):
            return PaymentStatus.PAID
        elif balance_due < total_amount:
            # Check if overdue even while partially paid
            if due_date_str:
                try:
                    due = date.fromisoformat(due_date_str)
                    if date.today() > due:
                        return PaymentStatus.OVERDUE
                except ValueError:
                    pass
            return PaymentStatus.PARTIAL
        else:
            # Full balance still unpaid
            if due_date_str:
                try:
                    due = date.fromisoformat(due_date_str)
                    if date.today() > due:
                        return PaymentStatus.OVERDUE
                except ValueError:
                    pass
            return PaymentStatus.PENDING

    def sync_invoice_status(self, qbo_invoice_id: str) -> Optional[InvoiceRecord]:
        """
        Queries QuickBooks Online for the latest balance of an invoice,
        records any new linked payments, and updates local ledger status.
        """
        local_inv = self.ledger.get_invoice_by_id(qbo_invoice_id)
        if not local_inv:
            return None

        # Fetch latest state from QBO
        qbo_inv = self.client.get_invoice(qbo_invoice_id)
        if not qbo_inv:
            return local_inv

        latest_balance = Decimal(str(qbo_inv.get("Balance", local_inv.balance_due)))
        new_status = self.determine_status(
            total_amount=local_inv.total_amount,
            balance_due=latest_balance,
            due_date_str=local_inv.due_date,
        )

        # Sync payments linked to this invoice
        payments_data = self.client.get_payments_for_invoice(qbo_invoice_id)
        for p in payments_data:
            pid = str(p.get("Id"))
            amount = Decimal(str(p.get("TotalAmt", 0)))
            txn_date = p.get("TxnDate", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
            ref_num = p.get("PaymentRefNum")
            method = p.get("PaymentMethodRef", {}).get("value", "CreditCard")

            pay_rec = PaymentRecord(
                qbo_payment_id=pid,
                qbo_invoice_id=qbo_invoice_id,
                amount=amount,
                payment_method=method,
                txn_date=txn_date,
                reference_num=ref_num,
                currency=local_inv.currency,
                raw_response=json.dumps(p),
            )
            self.ledger.record_payment(pay_rec)

        # Update invoice in ledger if balance or status changed
        if latest_balance != local_inv.balance_due or new_status != local_inv.payment_status:
            self.ledger.update_invoice_payment_status(
                qbo_invoice_id=qbo_invoice_id,
                balance_due=latest_balance,
                payment_status=new_status,
                raw_response=json.dumps(qbo_inv),
            )
            self.ledger.log_sync_event(
                SyncLogEntry(
                    event_type="INVOICE_STATUS_UPDATED",
                    entity_id=qbo_invoice_id,
                    status=new_status.value,
                    message=f"Invoice {local_inv.doc_number} updated: Balance {latest_balance}, Status {new_status.value}",
                    details={"previous_balance": float(local_inv.balance_due), "new_balance": float(latest_balance)},
                )
            )

        return self.ledger.get_invoice_by_id(qbo_invoice_id)

    def sync_all_pending(self) -> Tuple[int, int, List[Dict[str, Any]]]:
        """
        Scans all PENDING, PARTIAL, and OVERDUE invoices, querying QBO for updates.
        Returns: (total_checked, total_updated, summary_list)
        """
        all_invoices = self.ledger.list_invoices(limit=500)
        open_invoices = [inv for inv in all_invoices if inv.payment_status != PaymentStatus.PAID]

        checked = len(open_invoices)
        updated = 0
        summaries: List[Dict[str, Any]] = []

        for inv in open_invoices:
            prev_status = inv.payment_status
            prev_balance = inv.balance_due
            synced = self.sync_invoice_status(inv.qbo_invoice_id)

            if synced and (synced.payment_status != prev_status or synced.balance_due != prev_balance):
                updated += 1
                summaries.append({
                    "doc_number": synced.doc_number,
                    "customer": synced.customer_name,
                    "previous_status": prev_status.value,
                    "new_status": synced.payment_status.value,
                    "previous_balance": float(prev_balance),
                    "new_balance": float(synced.balance_due),
                })

        return checked, updated, summaries

    def record_manual_payment(
        self,
        qbo_invoice_id: str,
        amount: Decimal,
        payment_method: str = "CreditCard",
        reference_num: Optional[str] = None,
    ) -> PaymentRecord:
        """
        Explicitly records a payment both in QuickBooks Online and the local ledger.
        """
        inv = self.ledger.get_invoice_by_id(qbo_invoice_id)
        if not inv:
            raise ValueError(f"Invoice {qbo_invoice_id} does not exist in local database.")

        if amount <= Decimal("0.00"):
            raise ValueError("Payment amount must be greater than zero.")

        if amount > inv.balance_due:
            raise ValueError(f"Payment amount (${amount}) exceeds invoice balance (${inv.balance_due}).")

        # Post payment to QBO
        qbo_payment = self.client.record_payment(
            invoice_id=qbo_invoice_id,
            amount=float(amount),
            payment_method=payment_method,
            reference_num=reference_num,
        )

        pay_record = PaymentRecord(
            qbo_payment_id=str(qbo_payment.get("Id")),
            qbo_invoice_id=qbo_invoice_id,
            amount=amount,
            payment_method=payment_method,
            txn_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            reference_num=reference_num,
            currency=inv.currency,
            raw_response=json.dumps(qbo_payment),
        )
        self.ledger.record_payment(pay_record)

        # Trigger synchronization of invoice status
        self.sync_invoice_status(qbo_invoice_id)
        return pay_record
