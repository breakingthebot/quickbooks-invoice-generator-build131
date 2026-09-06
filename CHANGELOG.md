# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.0] - 2026-09-05

### Added
- **Native Android Application (`android/`)**:
  - Production-grade mobile client built with Kotlin 2.0.21, Jetpack Compose, Material 3, and Retrofit 2.
  - Live Executive Dashboard featuring Financial KPI cards (Invoiced, Collected, Outstanding, Overdue) and horizontal AR Aging Schedule card scroll.
  - Invoice Ledger screen with real-time status filtering chips (`ALL`, `PENDING`, `PARTIAL`, `PAID`, `OVERDUE`, `VOIDED`) and search bar.
  - One-click `RecordPaymentDialog` supporting multiple payment methods (`CreditCard`, `BankTransfer`, `Check`, `Cash`) with reference tracking.
  - Interactive `CreateInvoiceScreen` wizard with customer information, Net terms, dynamic line items repeater, tax rate %, shipping fees, and live total math.
  - Activity screen displaying tabbed audit feeds for dispatched dunning notices and QuickBooks Online webhooks.
  - Configurable in-app backend base URL switcher (`ServerSettingsDialog`) supporting Android Emulator (`http://10.0.2.2:8000/`), local WiFi IPs, and ngrok/Cloudflare tunnels.
  - Network security configuration allowing cleartext traffic for local development.
  - Standalone Gradle build with wrapper (`gradle-8.11.1-bin.zip`), JDK 17 support, and complete unit tests (`QbModelsTest`).
- **Documentation**:
  - Created `android/README.md` with Android Studio instructions, build commands, and network setup.
  - Created `docs/summaries/iteration_05_summary.md`.

## [1.3.0] - 2026-09-05

### Added
- **Vercel-Ready Next.js 14 Web Application (`web/`)**:
  - Full-featured web application built with Next.js 14 (App Router), React 18, TypeScript 5.6, and Tailwind CSS.
  - Vercel cloud deployment configuration (`vercel.json`) supporting 1-click deployments.
  - Interactive Invoice Creation Modal wizard with dynamic line items, taxes, discounts, and real-time total computation.
  - One-click Payment Settlement Modal with balance updates.
  - Accounts Receivable Aging Schedule card grid with live bucket totals.
  - Automated Dunning Escalation trigger button with immediate visual feedback.
  - Real-time audit feeds for dunning notices and cryptographic HMAC-SHA256 webhook deliveries.
- **Backend CORS Middleware (`src/qb_invoicing/api.py`)**:
  - Configured `CORSMiddleware` on FastAPI to support cross-origin API calls from Vercel (`*.vercel.app`), local development servers (`http://localhost:3000`), and mobile clients.
- **Documentation & Guides**:
  - Created `web/README.md` with local development commands and Vercel deployment workflows.
  - Created `docs/summaries/iteration_04_summary.md`.

## [1.2.0] - 2026-09-05

### Added
- **Automated Dunning & Escalation Engine (`src/qb_invoicing/dunning.py`)**:
  - Four escalation severity tiers: Tier 1 Friendly (1-14d), Tier 2 Urgent (15-30d), Tier 3 Final Demand (31-60d), and Tier 4 Collections Warning (61+d).
  - Dynamic template generator for plain-text and responsive HTML email notices with color-coded badges, balance summaries, and direct payment portal links.
  - Frequency cooldown guard (default 7 days) to prevent over-contacting customers, with optional bypass flag.
  - Batch cycle execution method (`run_dunning_cycle`) evaluating all open accounts receivable.
- **Accounts Receivable Aging Schedule Schedule**:
  - Dynamic aging bucket categorization: `Current`, `1-30 Days`, `31-60 Days`, `61-90 Days`, and `90+ Days`.
  - Aging report generator with per-bucket totals and detailed invoice breakdowns.
- **Ledger Persistence & Audit Trail**:
  - New `dunning_history` table in SQLite tracking notice dispatches, escalation levels, days overdue, balances, and timestamps.
  - Ledger methods for notice recording, history retrieval, and cooldown lookups.
- **REST API & Web Dashboard Enhancements**:
  - REST endpoints: `GET /api/dunning/aging-report`, `GET /api/dunning/history`, `POST /api/dunning/run`, and `POST /api/dunning/evaluate/{id}`.
  - Interactive Web Dashboard (`GET /`): Aging schedule visual card grid, "Run Dunning Escalation" one-click action, and live dunning audit history feed.
- **CLI Commands**:
  - `qb-invoicing aging-report [--as-of]`: Prints Rich formatted accounts receivable aging schedule and invoice breakdown.
  - `qb-invoicing dunning-run [--as-of, --cooldown-days, --force, --dry-run]`: Executes automated dunning cycle.
  - `qb-invoicing dunning-history [--limit]`: Displays past dunning escalation notices.
- **Expanded Test Suite**:
  - Added `tests/test_dunning.py` and updated `tests/test_api.py` and `tests/test_cli.py` (total **43 passing tests**).

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
