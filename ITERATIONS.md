# Iterations & Git Commit Log

**Project**: QuickBooks Online Invoice Generator & Payment Status Tracker (Build 131)  
**Repository**: [https://github.com/breakingthebot/quickbooks-invoice-generator-build131](https://github.com/breakingthebot/quickbooks-invoice-generator-build131)  
**Stack**: Python 3.12, SQLite, Click, Rich, Pydantic v2, HTTPX, Jinja2, Pytest  

This document logs every incremental engineering iteration and git commit pushed to the public repository.

---

## Iteration Overview Table

| Iteration | Git Commit | Version | Focus / Summary | Tests Passed | Full Summary Archive |
| :---: | :---: | :---: | :--- | :---: | :--- |
| **01** | [`76dd4f4`](https://github.com/breakingthebot/quickbooks-invoice-generator-build131/commit/76dd4f4) | `v1.0.0` | **Core QuickBooks Online Invoice Generator, Order Ingestion, Payment Status Tracker, Persistent Ledger & CLI**<br>Order data ingestion and validation, QBO Accounting API v3 mapping, native offline sandbox engine, SQLite persistent ledger, payment status lifecycle tracking, Rich CLI suite (`qb-invoicing`), and multi-platform CI workflow. | 21 / 21 | [Iteration 01 Summary](docs/summaries/iteration_01_summary.md) |
| **02** | `Pending` | `v1.1.0` | **QuickBooks Webhook Ingestion, Cryptographic Signature Verification, Automated Reconciliation & Real-Time Web Dashboard**<br>Intuit HMAC-SHA256 signature verification, webhook event deduplication, real-time payment reconciliation on `Payment.Create/Update`, invoice voiding, FastAPI REST API, and interactive Tailwind CSS web dashboard. | 33 / 33 | [Iteration 02 Summary](docs/summaries/iteration_02_summary.md) |

---

## Chronological Iteration Entries

### Iteration 2: QuickBooks Webhook Ingestion, Cryptographic Signature Verification, Automated Reconciliation & Real-Time Web Dashboard
- **Git Commit**: [`3e3b26f`](https://github.com/breakingthebot/quickbooks-invoice-generator-build131/commit/3e3b26f)
- **Tag / Version**: `v1.1.0`
- **Date**: 2026-09-05
- **Plain English Summary**:
  Added automated webhook processing from Intuit's event notification bus with cryptographic HMAC-SHA256 signature verification (`intuit-signature`). Implemented idempotency using a dedicated SQLite `webhook_events` table to prevent replay attacks and duplicate payments. Built automatic reconciliation that catches `Payment.Create` events, reconciles open invoices, records payments, and updates balances. Added full FastAPI REST API endpoints, an interactive Tailwind CSS web portal with live KPI cards and invoice status pills, and CLI commands (`qb-invoicing serve`, `qb-invoicing simulate-webhook`).
- **Key Files Introduced / Modified**:
  - `src/qb_invoicing/webhooks.py`: Cryptographic HMAC-SHA256 verification and event processor.
  - `src/qb_invoicing/api.py`: FastAPI REST API, webhook receiver, and Tailwind CSS dashboard.
  - `src/qb_invoicing/ledger.py`: Added `webhook_events` table, idempotency checks, and `void_invoice()`.
  - `src/qb_invoicing/cli.py`: Added `serve` and `simulate-webhook` commands.
  - `tests/test_webhooks.py`: Tests covering HMAC verification, payment handling, and idempotency.
  - `tests/test_api.py`: Tests covering REST endpoints and web dashboard.
  - `docs/summaries/iteration_02_summary.md`: Iteration 2 technical archive.
- **Test Results**: 33 Pytest unit & integration tests passing.

---

### Iteration 1: Core QuickBooks Online Invoice Generator, Order Ingestion, Payment Status Tracker, Persistent Ledger & CLI
- **Git Commit**: [`ee987f0`](https://github.com/breakingthebot/quickbooks-invoice-generator-build131/commit/ee987f0)
- **Tag / Version**: `v1.0.0`
- **Date**: 2026-09-05
- **Plain English Summary**:
  Built the foundational QuickBooks Online invoice generation engine and payment status tracking system. Implemented robust order ingestion parsing e-commerce/ERP orders into normalized line items, tax breakdowns, discounts, and shipping lines. Created a QuickBooks Online Accounting API v3 transformer producing compliant JSON payloads and a client supporting both live Intuit API endpoints and a high-fidelity offline mock sandbox engine. Created a persistent SQLite ledger with foreign key constraints, tracking invoice lifecycles (`PENDING` -> `PARTIAL` -> `PAID`, `OVERDUE`) and payment history. Built an installable CLI (`qb-invoicing`) featuring invoice generation, batch processing, live status inspection, payment recording, and financial KPI metrics reporting.
- **Key Files Introduced**:
  - `src/qb_invoicing/models.py`: Domain models for orders, items, addresses, QBO payload schemas, and ledger records.
  - `src/qb_invoicing/transformer.py`: Order-to-QBO transformation and calculations.
  - `src/qb_invoicing/qbo_client.py`: QBO API v3 client with persistent mock sandbox engine.
  - `src/qb_invoicing/ledger.py`: SQLite repository with transactions, indexes, and metrics.
  - `src/qb_invoicing/payment_tracker.py`: Payment reconciliation and status synchronization engine.
  - `src/qb_invoicing/renderer.py`: HTML and terminal invoice formatting.
  - `src/qb_invoicing/cli.py`: Click/Rich CLI suite (`qb-invoicing`).
  - `src/qb_invoicing/config.py`: Settings and environment variable loader.
  - `tests/`: 21 comprehensive unit and integration tests across 6 test modules.
  - `.github/workflows/ci.yml`: GitHub Actions continuous integration workflow.
- **Test Results**: 21 Pytest unit & integration tests passing (1.65s).
