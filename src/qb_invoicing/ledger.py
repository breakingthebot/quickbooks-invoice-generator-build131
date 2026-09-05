"""
SQLite persistent storage repository and ledger for invoices, orders, and payment tracking.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from qb_invoicing.models import (
    FinancialMetrics,
    InvoiceRecord,
    OrderData,
    PaymentRecord,
    PaymentStatus,
    SyncLogEntry,
)


class LedgerRepository:
    """Handles local database transactions and tracking states."""

    def __init__(self, db_path: str = "storage/qbo_invoicing.db"):
        self.db_path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self) -> None:
        """Initialize database schema with tables and indexes."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Orders table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    order_number TEXT,
                    customer_name TEXT NOT NULL,
                    customer_email TEXT NOT NULL,
                    total_amount REAL NOT NULL,
                    currency TEXT DEFAULT 'USD',
                    order_date TEXT NOT NULL,
                    raw_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            # Invoices table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS invoices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    qbo_invoice_id TEXT UNIQUE NOT NULL,
                    order_id TEXT NOT NULL,
                    doc_number TEXT NOT NULL,
                    customer_name TEXT NOT NULL,
                    customer_email TEXT NOT NULL,
                    txn_date TEXT NOT NULL,
                    due_date TEXT,
                    total_amount REAL NOT NULL,
                    balance_due REAL NOT NULL,
                    payment_status TEXT NOT NULL,
                    currency TEXT DEFAULT 'USD',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    raw_payload TEXT,
                    raw_response TEXT,
                    FOREIGN KEY (order_id) REFERENCES orders (order_id) ON DELETE CASCADE
                )
            """)

            # Payments table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    qbo_payment_id TEXT UNIQUE NOT NULL,
                    qbo_invoice_id TEXT NOT NULL,
                    amount REAL NOT NULL,
                    payment_method TEXT DEFAULT 'CreditCard',
                    txn_date TEXT NOT NULL,
                    reference_num TEXT,
                    currency TEXT DEFAULT 'USD',
                    created_at TEXT NOT NULL,
                    raw_response TEXT,
                    FOREIGN KEY (qbo_invoice_id) REFERENCES invoices (qbo_invoice_id) ON DELETE CASCADE
                )
            """)

            # Sync Audit Logs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details TEXT
                )
            """)

            # Webhook events table for idempotency
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS webhook_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    realm_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    entity_name TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    processed_at TEXT NOT NULL
                )
            """)

            # Indexes for high performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices (payment_status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoices_doc_number ON invoices (doc_number)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoices_order_id ON invoices (order_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_invoice ON payments (qbo_invoice_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_webhook_events_id ON webhook_events (event_id)")
            conn.commit()

    def save_order(self, order: OrderData) -> None:
        """Store incoming order snapshot."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO orders (
                    order_id, order_number, customer_name, customer_email,
                    total_amount, currency, order_date, raw_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order.order_id,
                    order.order_number or f"ORD-{order.order_id}",
                    order.customer.name,
                    order.customer.email,
                    float(order.computed_total),
                    order.currency,
                    order.order_date.isoformat(),
                    order.model_dump_json(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()

    def save_invoice(self, record: InvoiceRecord) -> InvoiceRecord:
        """Insert or update an invoice tracking record."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO invoices (
                    qbo_invoice_id, order_id, doc_number, customer_name, customer_email,
                    txn_date, due_date, total_amount, balance_due, payment_status,
                    currency, created_at, updated_at, raw_payload, raw_response
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(qbo_invoice_id) DO UPDATE SET
                    balance_due = excluded.balance_due,
                    payment_status = excluded.payment_status,
                    updated_at = excluded.updated_at,
                    raw_response = excluded.raw_response
                """,
                (
                    record.qbo_invoice_id,
                    record.order_id,
                    record.doc_number,
                    record.customer_name,
                    record.customer_email,
                    record.txn_date,
                    record.due_date,
                    float(record.total_amount),
                    float(record.balance_due),
                    record.payment_status.value,
                    record.currency,
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                    record.raw_payload,
                    record.raw_response,
                ),
            )
            if not record.id:
                record.id = cursor.lastrowid
            conn.commit()
        return record

    def update_invoice_payment_status(
        self,
        qbo_invoice_id: str,
        balance_due: Decimal,
        payment_status: PaymentStatus,
        raw_response: Optional[str] = None,
    ) -> bool:
        """Update balance and status of an invoice."""
        with self._get_connection() as conn:
            now_iso = datetime.now(timezone.utc).isoformat()
            if raw_response:
                cursor = conn.execute(
                    """
                    UPDATE invoices
                    SET balance_due = ?, payment_status = ?, updated_at = ?, raw_response = ?
                    WHERE qbo_invoice_id = ?
                    """,
                    (float(balance_due), payment_status.value, now_iso, raw_response, qbo_invoice_id),
                )
            else:
                cursor = conn.execute(
                    """
                    UPDATE invoices
                    SET balance_due = ?, payment_status = ?, updated_at = ?
                    WHERE qbo_invoice_id = ?
                    """,
                    (float(balance_due), payment_status.value, now_iso, qbo_invoice_id),
                )
            conn.commit()
            return cursor.rowcount > 0

    def record_payment(self, payment: PaymentRecord) -> PaymentRecord:
        """Record a payment transaction linked to an invoice."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO payments (
                    qbo_payment_id, qbo_invoice_id, amount, payment_method,
                    txn_date, reference_num, currency, created_at, raw_response
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payment.qbo_payment_id,
                    payment.qbo_invoice_id,
                    float(payment.amount),
                    payment.payment_method,
                    payment.txn_date,
                    payment.reference_num,
                    payment.currency,
                    payment.created_at.isoformat(),
                    payment.raw_response,
                ),
            )
            if not payment.id:
                payment.id = cursor.lastrowid
            conn.commit()
        return payment

    def log_sync_event(self, entry: SyncLogEntry) -> None:
        """Append an entry to the audit log."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO sync_audit_logs (timestamp, event_type, entity_id, status, message, details)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.timestamp.isoformat(),
                    entry.event_type,
                    entry.entity_id,
                    entry.status,
                    entry.message,
                    json.dumps(entry.details or {}),
                ),
            )
            conn.commit()

    def get_invoice_by_id(self, qbo_invoice_id: str) -> Optional[InvoiceRecord]:
        """Fetch invoice by QuickBooks Online invoice ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM invoices WHERE qbo_invoice_id = ?",
                (str(qbo_invoice_id),),
            ).fetchone()
            if row:
                return self._row_to_invoice(row)
        return None

    def get_invoice_by_doc_number(self, doc_number: str) -> Optional[InvoiceRecord]:
        """Fetch invoice by DocNumber."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM invoices WHERE doc_number = ?",
                (doc_number,),
            ).fetchone()
            if row:
                return self._row_to_invoice(row)
        return None

    def get_invoice_by_order_id(self, order_id: str) -> Optional[InvoiceRecord]:
        """Fetch invoice by Order ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM invoices WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            if row:
                return self._row_to_invoice(row)
        return None

    def list_invoices(
        self,
        status: Optional[PaymentStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[InvoiceRecord]:
        """List invoices with optional status filter."""
        with self._get_connection() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM invoices WHERE payment_status = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                    (status.value, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM invoices ORDER BY id DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            return [self._row_to_invoice(r) for r in rows]

    def get_payments_for_invoice(self, qbo_invoice_id: str) -> List[PaymentRecord]:
        """Get all payments applied to a specific invoice."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM payments WHERE qbo_invoice_id = ? ORDER BY id ASC",
                (qbo_invoice_id,),
            ).fetchall()
            payments = []
            for r in rows:
                payments.append(
                    PaymentRecord(
                        id=r["id"],
                        qbo_payment_id=r["qbo_payment_id"],
                        qbo_invoice_id=r["qbo_invoice_id"],
                        amount=Decimal(str(r["amount"])),
                        payment_method=r["payment_method"],
                        txn_date=r["txn_date"],
                        reference_num=r["reference_num"],
                        currency=r["currency"],
                        created_at=datetime.fromisoformat(r["created_at"]),
                        raw_response=r["raw_response"],
                    )
                )
            return payments

    def get_metrics(self) -> FinancialMetrics:
        """Compute aggregated metrics across all recorded invoices."""
        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT 
                    COUNT(*) as total_invoices,
                    COALESCE(SUM(total_amount), 0.0) as total_invoiced,
                    COALESCE(SUM(total_amount - balance_due), 0.0) as total_collected,
                    COALESCE(SUM(balance_due), 0.0) as total_outstanding,
                    SUM(CASE WHEN payment_status = 'PAID' THEN 1 ELSE 0 END) as paid_count,
                    SUM(CASE WHEN payment_status = 'PARTIAL' THEN 1 ELSE 0 END) as partial_count,
                    SUM(CASE WHEN payment_status = 'PENDING' THEN 1 ELSE 0 END) as pending_count,
                    SUM(CASE WHEN payment_status = 'OVERDUE' THEN 1 ELSE 0 END) as overdue_count
                FROM invoices
            """).fetchone()

            if not row:
                return FinancialMetrics()

            return FinancialMetrics(
                total_invoices=row["total_invoices"],
                total_invoiced_amount=Decimal(str(round(row["total_invoiced"], 2))),
                total_collected_amount=Decimal(str(round(row["total_collected"], 2))),
                total_outstanding_balance=Decimal(str(round(row["total_outstanding"], 2))),
                paid_invoices_count=row["paid_count"] or 0,
                partial_invoices_count=row["partial_count"] or 0,
                pending_invoices_count=row["pending_count"] or 0,
                overdue_invoices_count=row["overdue_count"] or 0,
            )

    def is_webhook_event_processed(self, event_id: str) -> bool:
        """Check whether a webhook event has already been processed."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM webhook_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            return row is not None

    def record_webhook_event(
        self,
        event_id: str,
        realm_id: str,
        event_type: str,
        entity_name: str,
        entity_id: str,
        operation: str,
        payload: str,
    ) -> bool:
        """Store a webhook event to guarantee at-most-once processing."""
        with self._get_connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO webhook_events (
                        event_id, realm_id, event_type, entity_name, entity_id, operation, payload, processed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        realm_id,
                        event_type,
                        entity_name,
                        entity_id,
                        operation,
                        payload,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def void_invoice(self, qbo_invoice_id: str) -> bool:
        """Mark an invoice as VOIDED in the ledger."""
        with self._get_connection() as conn:
            now_iso = datetime.now(timezone.utc).isoformat()
            cursor = conn.execute(
                """
                UPDATE invoices
                SET payment_status = ?, balance_due = 0.0, updated_at = ?
                WHERE qbo_invoice_id = ?
                """,
                (PaymentStatus.VOIDED.value, now_iso, str(qbo_invoice_id)),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_recent_webhook_events(self, limit: int = 25) -> List[Dict[str, Any]]:
        """Retrieve latest webhook events received."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM webhook_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def _row_to_invoice(self, r: sqlite3.Row) -> InvoiceRecord:
        return InvoiceRecord(
            id=r["id"],
            qbo_invoice_id=r["qbo_invoice_id"],
            order_id=r["order_id"],
            doc_number=r["doc_number"],
            customer_name=r["customer_name"],
            customer_email=r["customer_email"],
            txn_date=r["txn_date"],
            due_date=r["due_date"],
            total_amount=Decimal(str(r["total_amount"])),
            balance_due=Decimal(str(r["balance_due"])),
            payment_status=PaymentStatus(r["payment_status"]),
            currency=r["currency"],
            created_at=datetime.fromisoformat(r["created_at"]),
            updated_at=datetime.fromisoformat(r["updated_at"]),
            raw_payload=r["raw_payload"],
            raw_response=r["raw_response"],
        )
