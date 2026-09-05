# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-09-05

### Added
- **Intuit QuickBooks Webhook Processing Engine**:
  - HMAC-SHA256 signature verification (`intuit-signature` header) with constant-time digest comparison.
  - Automatic reconciliation for `Payment.Create`, `Payment.Update`, `Invoice.Update`, and `Invoice.Void` events.
  - Idempotency protection with persistent `webhook_events` tracking table.
- **FastAPI REST API & Interactive Web Dashboard**:
  - Webhook endpoint (`POST /api/webhooks/quickbooks`) with cryptographic validation.
  - REST endpoints for invoice querying, single invoice detail, order-to-invoice conversion, and payment recording.
  - Responsive web dashboard (Tailwind CSS) at `GET /` featuring financial KPI cards, live invoice status table, and printable HTML links.
- **CLI Management Commands**:
  - `qb-invoicing serve [--host, --port]`: Launches the web dashboard and webhook server via Uvicorn.
  - `qb-invoicing simulate-webhook [--entity, --operation, --id]`: Generates and triggers signed Intuit webhook payloads.
- **Extended Test Suite**:
  - Added 12 new unit and integration tests across `tests/test_webhooks.py` and `tests/test_api.py` (total 33 tests passing).

## [1.0.0] - 2026-09-05

### Added
- **Core Order Ingestion Engine**:
  - Pydantic v2 schemas (`OrderData`, `OrderCustomer`, `OrderItem`, `Address`) with automated tax, subtotal, discount, and shipping fee arithmetic.
  - Multi-tier sample order files (`sample_order_ecommerce.json`, `sample_order_consulting.json`, `sample_orders_batch.json`).
- **QuickBooks Online Accounting API v3 Transformer**:
  - `OrderTransformer` mapping order structures to Intuit Accounting API v3 `QBOInvoicePayload`.
  - Automatic `SalesItemLineDetail`, `DiscountLineDetail`, and shipping line generation.
  - Dynamic payment terms calculation (Net 30, Due Upon Receipt).
- **QuickBooks Online API Client & Offline Mock Engine**:
  - `QuickBooksClient` supporting authenticated live sandbox/production endpoints via OAuth2 Bearer tokens.
  - `MockQBOEngine` simulating Intuit Accounting v3 REST endpoints (`/invoice`, `/customer`, `/payment`, `/query`) with persistent state (`storage/.mock_qbo_state.json`).
- **SQLite Persistence Ledger**:
  - `LedgerRepository` managing `orders`, `invoices`, `payments`, and `sync_audit_logs`.
  - Foreign key constraints, indexing on `doc_number` and `payment_status`, and financial KPI aggregations (`get_metrics`).
- **Payment Status Tracker & Reconciliation Engine**:
  - Lifecycle state engine tracking transitions (`PENDING`, `PARTIAL`, `PAID`, `OVERDUE`).
  - Automated status syncing and manual payment recording.
- **Installable CLI Suite (`qb-invoicing`)**:
  - CLI commands: `--version`, `init-db`, `generate`, `batch-generate`, `status`, `record-payment`, `sync-payments`, `list-invoices`, `metrics`, `preview`.
- **Testing & Continuous Integration**:
  - 21 Pytest unit and integration tests passing in 1.65s.
  - GitHub Actions CI workflow covering Ubuntu and Windows on Python 3.10, 3.11, and 3.12.
- **Documentation & Legal**:
  - Standard MIT License (`LICENSE`).
  - Architectural documentation and CLI usage guide in `README.md`.
  - Iteration audit logging in `ITERATIONS.md`.
