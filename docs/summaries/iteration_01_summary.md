# Engineering Summary — Iteration 01: Core QuickBooks Online Invoice Generation Engine & Payment Tracker

**Build Reference**: Build 131  
**Version**: `v1.0.0`  
**Status**: Completed & Verified  

---

## 1. Overview & Objective

The primary objective of Iteration 1 was to engineer a production-grade QuickBooks Online (QBO) invoice generator and real-time payment status tracker (`qb-invoicing`). The system consumes structured order data (from JSON, e-commerce webhooks, or ERP exports), normalizes and validates order lines, tax rates, shipping, and discounts, transforms them into the official QuickBooks Online Accounting API v3 JSON schema, synchronizes them with QuickBooks Online (supporting both live Intuit OAuth2 endpoints and a high-fidelity offline mock sandbox engine), and maintains a persistent SQLite ledger of all tracked invoices, customer mappings, payment records, and financial metrics.

---

## 2. Key Architecture & Modules Introduced

### `qb_invoicing/models.py`
- **Domain Entities**: `OrderCustomer`, `OrderItem`, `Address`, `OrderData`.
- **Validation**: Enforces non-negative pricing, positive line quantities, mathematical line subtotal rounding (`ROUND_HALF_UP`), and taxable subtotal calculations.
- **QuickBooks Online API v3 Node Schemas**: `QBOReference`, `QBOLine`, `QBOSalesItemLineDetail`, `QBOInvoicePayload`.
- **Ledger Records**: `InvoiceRecord`, `PaymentRecord`, `SyncLogEntry`, `FinancialMetrics`.
- **Lifecycle Enums**: `PaymentStatus` (`DRAFT`, `PENDING`, `SENT`, `PARTIAL`, `PAID`, `OVERDUE`, `VOIDED`).

### `qb_invoicing/transformer.py`
- **`OrderTransformer`**: Converts high-level order models into strict Intuit Accounting API v3 JSON payloads.
- Resolves customer references with optional fallback or override.
- Formats line items (`SalesItemLineDetail` with `ItemRef`, `TaxCodeRef`, `UnitPrice`, `Qty`).
- Automatically appends explicit lines for shipping fees and discounts.
- Automatically calculates invoice payment due dates based on configured payment terms (e.g. Net 30).
- Formats addresses into QBO `PhysicalAddress` structure.

### `qb_invoicing/qbo_client.py`
- **`QuickBooksClient`**: Unified client managing HTTP communication with Intuit QuickBooks Online Accounting API v3 (`/invoice`, `/customer`, `/payment`, `/query`).
- **`MockQBOEngine`**: Realistic offline sandbox engine simulating Intuit's cloud backend. Maintains persistent mock state (`storage/.mock_qbo_state.json`), auto-generates sequential IDs (`SyncToken`, `Id`), supports SQL query filters (`select * from Invoice where DocNumber = ...`), and updates balances upon recording payments.
- Allows 100% offline verification without live Intuit credentials.

### `qb_invoicing/ledger.py`
- **`LedgerRepository`**: Thread-safe SQLite persistence engine.
- Manages tables: `orders`, `invoices`, `payments`, `sync_audit_logs`.
- Enforces relational foreign key cascades (`FOREIGN KEY (order_id) REFERENCES orders(order_id)`).
- Provides transaction methods: `save_order`, `save_invoice`, `update_invoice_payment_status`, `record_payment`, `get_invoice_by_id`, `get_invoice_by_doc_number`, `list_invoices`, and aggregated `get_metrics()`.

### `qb_invoicing/payment_tracker.py`
- **`PaymentStatusTracker`**: Core reconciliation service.
- Determines invoice state transitions based on live balance and due date (`PENDING` -> `PARTIAL` -> `PAID`, or `OVERDUE` when `date.today() > due_date`).
- Syncs individual invoices or batches of open invoices against QuickBooks Online.
- Logs accounting audit events in `sync_audit_logs`.

### `qb_invoicing/renderer.py`
- **`InvoiceRenderer`**: Renders clean ASCII/Unicode terminal summaries and standalone HTML invoice documents with color-coded status badges and line item breakdowns.

### `qb_invoicing/cli.py`
- **Command Line Suite (`qb-invoicing`)**:
  - `qb-invoicing --version`: CLI version display (`v1.0.0`).
  - `qb-invoicing init-db`: Database initialization and schema verification.
  - `qb-invoicing generate`: Generates invoice from order JSON with optional HTML export.
  - `qb-invoicing batch-generate`: Ingests an array of orders and creates batch invoices.
  - `qb-invoicing status`: Displays live status card and payment history.
  - `qb-invoicing record-payment`: Records manual payments and updates balances.
  - `qb-invoicing sync-payments`: Scans open invoices and reconciles with QuickBooks Online.
  - `qb-invoicing list-invoices`: Lists invoices with status filters.
  - `qb-invoicing metrics`: Displays financial KPI summary.
  - `qb-invoicing preview`: Validates order and previews QBO JSON without creating.

---

## 3. Test Suite Verification

- **Test Framework**: Pytest 9.1+ with `pytest-mock`
- **Total Tests Executed**: 21
- **Tests Passing**: 21 / 21 (100%)
- **Execution Time**: 1.65 seconds
- **Coverage Areas**:
  - `tests/test_models.py`: Model validations, address formatting, tax/subtotal calculation.
  - `tests/test_transformer.py`: Order-to-QBO transformation, discounts, shipping lines, terms.
  - `tests/test_qbo_client.py`: Customer creation, invoice generation, payment processing in mock engine.
  - `tests/test_ledger.py`: SQLite persistence, foreign key integrity, query methods, metrics aggregation.
  - `tests/test_payment_tracker.py`: Status calculation, payment recording, balance reconciliation.
  - `tests/test_cli.py`: End-to-end CLI commands via Click `CliRunner`.
