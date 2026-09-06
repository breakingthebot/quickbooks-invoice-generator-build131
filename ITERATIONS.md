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
| **02** | [`e34f8c0`](https://github.com/breakingthebot/quickbooks-invoice-generator-build131/commit/e34f8c0) | `v1.1.0` | **QuickBooks Webhook Ingestion, Cryptographic Signature Verification, Automated Reconciliation & Real-Time Web Dashboard**<br>Intuit HMAC-SHA256 signature verification, webhook event deduplication, real-time payment reconciliation on `Payment.Create/Update`, invoice voiding, FastAPI REST API, and interactive Tailwind CSS web dashboard. | 33 / 33 | [Iteration 02 Summary](docs/summaries/iteration_02_summary.md) |
| **03** | [`7307b17`](https://github.com/breakingthebot/quickbooks-invoice-generator-build131/commit/7307b17) | `v1.2.0` | **Automated Dunning Escalation & Accounts Receivable Aging Engine**<br>Automated overdue payment escalation ladder (Net 15, Net 30, Net 60, Net 90+ buckets), customizable HTML & plain-text dunning templates, frequency cooldown spam suppression, SQLite dunning audit ledger, REST API endpoints, aging schedule web dashboard integration, and CLI commands (`aging-report`, `dunning-run`, `dunning-history`). | 43 / 43 | [Iteration 03 Summary](docs/summaries/iteration_03_summary.md) |
| **04** | [`9802fe1`](https://github.com/breakingthebot/quickbooks-invoice-generator-build131/commit/9802fe1) | `v1.3.0` | **Vercel-Ready Next.js 14 Web Application**<br>Full-featured Next.js 14 (App Router) + React 18 + TypeScript + Tailwind CSS web portal in `web/` configured for 1-click Vercel deployment (`vercel.json`), interactive Invoice Creation wizard modal, one-click Payment Settlement modal, Accounts Receivable Aging schedule visual cards, automated Dunning Escalation trigger, live audit feeds, and backend FastAPI CORS middleware. | 43 / 43 + Next.js build | [Iteration 04 Summary](docs/summaries/iteration_04_summary.md) |
| **05** | [`a4a06a0`](https://github.com/breakingthebot/quickbooks-invoice-generator-build131/commit/a4a06a0) | `v1.4.0` | **Native Android Mobile Application (Kotlin & Jetpack Compose)**<br>Enterprise Android mobile client in `android/` built with Kotlin 2.0.21, Jetpack Compose, Material 3, and Retrofit 2. Features real-time Financial KPI cards, Accounts Receivable Aging Schedule card scroll, status-filtered Invoice Ledger, dynamic "Record Payment" settlement dialog, full-featured "Create QBO Invoice" wizard with line items repeater and live math calculations, Dunning notices and Webhook activity feeds, dynamic server URL switcher, and standalone Gradle test suite. | 43 / 43 Pytest + 4 / 4 Android | [Iteration 05 Summary](docs/summaries/iteration_05_summary.md) |
| **06** | [`8b9c941`](https://github.com/breakingthebot/quickbooks-invoice-generator-build131/commit/8b9c941) | `v1.5.0` | **Multi-Gateway Payment Checkout & Stripe / ACH Auto-Settlement Engine**<br>Customer-facing Stripe Checkout session generator, hosted payment portal (`/pay`), cryptographic Stripe HMAC-SHA256 webhook listener (`POST /api/webhooks/stripe`), automatic reconciliation into QBO Payment entities and SQLite ledger, CLI commands (`checkout`, `simulate-stripe-payment`), and dunning email portal link integration. | 59 / 59 | [Iteration 06 Summary](docs/summaries/iteration_06_summary.md) |

---

## Chronological Iteration Entries

### Iteration 6: Multi-Gateway Payment Checkout & Stripe / ACH Auto-Settlement Engine
- **Git Commit**: [`8b9c941`](https://github.com/breakingthebot/quickbooks-invoice-generator-build131/commit/8b9c941)
- **Tag / Version**: `v1.5.0`
- **Date**: 2026-09-05
- **Plain English Summary**:
  Delivered an enterprise-grade multi-gateway self-service payment checkout and settlement engine supporting credit cards, Apple Pay, Google Pay, and US ACH bank transfers. Implemented cryptographic Stripe webhook signature verification (`Stripe-Signature` HMAC-SHA256 with timestamp tolerance) to auto-settle customer payments directly into QuickBooks Online `Payment` entities and update SQLite ledger balances with idempotency guarantees. Built customer-facing hosted checkout portal pages (`/pay/{identifier}`), an offline sandbox checkout simulator (`/pay/checkout/{session_id}`), and a receipt confirmation screen (`/pay/success/{identifier}`). Added CLI commands (`checkout`, `simulate-stripe-payment`) and integrated direct payment URLs into automated dunning reminder notices.
- **Key Files Introduced / Modified**:
  - `src/qb_invoicing/stripe_engine.py`: Core Stripe Checkout Session generation, HMAC-SHA256 webhook verification, and automated QBO/ledger reconciliation engine.
  - `src/qb_invoicing/models.py`: Added `StripeCheckoutSession` and `StripePaymentIntentResult` schemas.
  - `src/qb_invoicing/config.py`: Added Stripe gateway configuration settings (`stripe_api_key`, `stripe_webhook_secret`, `stripe_use_mock`).
  - `src/qb_invoicing/payment_tracker.py`: Added `record_direct_payment` method to encapsulate gateway reconciliation and status updates.
  - `src/qb_invoicing/api.py`: Added `/api/invoices/{id}/checkout-session`, `/api/webhooks/stripe`, `/api/pay/simulate`, and hosted portal HTML views (`/pay/{id}`, `/pay/checkout/{session_id}`, `/pay/success/{id}`).
  - `src/qb_invoicing/cli.py`: Added `checkout` and `simulate-stripe-payment` CLI commands and enhanced `serve` startup output.
  - `src/qb_invoicing/dunning.py`: Integrated direct payment links (`/pay/{invoice_id}`) into dunning notice templates.
  - `tests/test_stripe.py`: 16 comprehensive unit and integration tests covering sessions, crypto, webhooks, portal pages, and CLI commands.
  - `docs/summaries/iteration_06_summary.md`: Iteration 6 technical documentation.
- **Test Results**: 59 / 59 Pytest unit and integration tests passing.

---

### Iteration 5: Native Android Mobile Application (Kotlin & Jetpack Compose)
- **Git Commit**: [`a4a06a0`](https://github.com/breakingthebot/quickbooks-invoice-generator-build131/commit/a4a06a0)
- **Tag / Version**: `v1.4.0`
- **Date**: 2026-09-05
- **Plain English Summary**:
  Delivered a complete, production-grade native Android application in `android/` using Kotlin, Jetpack Compose, Material 3, and Retrofit 2. The mobile app connects to the QuickBooks FastAPI REST backend and gives operators full mobile capability: an Executive Financial Dashboard with KPI cards and Aging Schedule buckets, an Invoice Ledger with status filtering chips and search, a modal payment settlement dialog, an interactive invoice creation wizard with dynamic line items and real-time total computation, and a split activity log for dispatched dunning notices and QuickBooks webhooks. Configured with a dynamic endpoint switcher to test against Android Emulator (`http://10.0.2.2:8000/`), local WiFi IPs, or public tunnels (ngrok). Configured standalone Gradle 8.11 with wrapper, network security configurations for local HTTP traffic, and unit tests.
- **Key Files Introduced / Modified**:
  - `android/build.gradle.kts`, `android/settings.gradle.kts`, `android/gradle.properties`: Root Gradle build scripts.
  - `android/app/build.gradle.kts`: Android application module with Compose BOM, Material 3, Retrofit, and Coroutines.
  - `android/app/src/main/AndroidManifest.xml` & `network_security_config.xml`: Permissions and cleartext config.
  - `android/app/src/main/java/.../data/`: `Models.kt`, `ApiClient.kt`, `QbApiService.kt`, `QbRepository.kt`.
  - `android/app/src/main/java/.../ui/`: `MainActivity.kt`, `MainViewModel.kt`, `DashboardScreen.kt`, `InvoicesScreen.kt`, `CreateInvoiceScreen.kt`, `ActivityScreen.kt`, `CommonComponents.kt`, `Theme.kt`.
  - `android/app/src/test/.../QbModelsTest.kt`: Unit tests for domain models and pricing calculations.
  - `android/README.md`: Android developer documentation and Studio setup.
  - `docs/summaries/iteration_05_summary.md`: Iteration 5 technical summary archive.
- **Test Results**: 43 Pytest unit & integration tests passing; 4 / 4 Android unit tests passing (`./gradlew testDebugUnitTest`).

---

### Iteration 4: Vercel-Ready Next.js 14 Web Application
- **Git Commit**: [`9802fe1`](https://github.com/breakingthebot/quickbooks-invoice-generator-build131/commit/9802fe1)
- **Tag / Version**: `v1.3.0`
- **Date**: 2026-09-05
- **Plain English Summary**:
  Delivered a modern, production-grade Next.js 14 web application in the `web/` directory, configured for zero-configuration 1-click Vercel cloud deployment. Features a responsive Tailwind CSS dashboard with interactive KPI scorecards, Accounts Receivable Aging Schedule card grid, an interactive "Create Invoice" modal with real-time tax/shipping/discount math, a "Record Payment" settlement modal, a one-click Dunning Escalation runner, and live split feeds for sent dunning notices and cryptographic QuickBooks webhooks. Enabled CORS middleware on FastAPI to seamlessly support external web and mobile clients.
- **Key Files Introduced / Modified**:
  - `vercel.json`: Root Vercel deployment configuration.
  - `web/package.json`, `web/tsconfig.json`, `web/next.config.mjs`, `web/tailwind.config.ts`: Next.js 14 environment.
  - `web/app/page.tsx`: Single-page interactive dashboard, creation modal, and payment modal.
  - `web/lib/api.ts`: Typed fetch API client and domain interfaces.
  - `web/app/layout.tsx` & `web/app/globals.css`: Layout navigation and styling.
  - `web/README.md`: Next.js development and Vercel cloud deployment documentation.
  - `src/qb_invoicing/api.py`: Configured `CORSMiddleware` on FastAPI service.
  - `docs/summaries/iteration_04_summary.md`: Iteration 4 technical summary archive.
- **Test Results**: 43 Pytest unit & integration tests passing; `npm run build` compiled cleanly.

---

### Iteration 3: Automated Dunning Escalation & Accounts Receivable Aging Engine
- **Git Commit**: [`7307b17`](https://github.com/breakingthebot/quickbooks-invoice-generator-build131/commit/7307b17)
- **Tag / Version**: `v1.2.0`
- **Date**: 2026-09-05
- **Plain English Summary**:
  Introduced an accounts receivable aging schedule engine and automated dunning workflow. Overdue invoices are grouped into standard aging buckets (Current, 1-30 Days, 31-60 Days, 61-90 Days, 90+ Days) and matched against a 4-tier escalation ladder (Friendly Reminder, Urgent Notice, Final Demand, Collections Warning). Built customizable Jinja2/HTML and plain-text reminder notices with dynamic payment portal links. Implemented frequency cooldown rules (default 7 days) to prevent customer fatigue. Added a dedicated `dunning_history` SQLite audit table, REST API endpoints (`/api/dunning/aging-report`, `/api/dunning/history`, `/api/dunning/run`, `/api/dunning/evaluate/{id}`), live web dashboard integration with interactive trigger buttons, and CLI commands (`qb-invoicing aging-report`, `qb-invoicing dunning-run`, `qb-invoicing dunning-history`).
- **Key Files Introduced / Modified**:
  - `src/qb_invoicing/dunning.py`: Escalation engine, aging calculator, cooldown rules, and notice template generator.
  - `src/qb_invoicing/models.py`: Domain models for `AgingBucket`, `DunningLevel`, `AgingScheduleReport`, and `DunningNoticeRecord`.
  - `src/qb_invoicing/ledger.py`: Added `dunning_history` table, `get_aging_report()`, `record_dunning_notice()`, and lookup methods.
  - `src/qb_invoicing/api.py`: Dunning REST endpoints and interactive Aging Schedule dashboard UI.
  - `src/qb_invoicing/cli.py`: Added `aging-report`, `dunning-run`, and `dunning-history` commands.
  - `tests/test_dunning.py`: 5 new unit/integration tests for dunning and aging logic.
  - `docs/summaries/iteration_03_summary.md`: Iteration 3 technical summary archive.
- **Test Results**: 43 Pytest unit & integration tests passing (7.09s).

---

### Iteration 2: QuickBooks Webhook Ingestion, Cryptographic Signature Verification, Automated Reconciliation & Real-Time Web Dashboard
- **Git Commit**: [`e34f8c0`](https://github.com/breakingthebot/quickbooks-invoice-generator-build131/commit/e34f8c0)
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
