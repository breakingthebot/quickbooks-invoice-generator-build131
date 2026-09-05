# Engineering Summary — Iteration 02: QuickBooks Webhook Ingestion, Cryptographic Signature Verification, Automated Reconciliation & Real-Time Web Dashboard

**Build Reference**: Build 131  
**Version**: `v1.1.0`  
**Status**: Completed & Verified  

---

## 1. Overview & Objective

The objective of Iteration 2 was to implement real-time webhook ingestion from Intuit's QuickBooks Online event notification bus, enforce strict cryptographic HMAC-SHA256 signature verification, achieve idempotent event processing, and build an interactive web dashboard and REST API using FastAPI.

---

## 2. Key Architecture & Modules Introduced / Enhanced

### `qb_invoicing/webhooks.py`
- **HMAC-SHA256 Signature Verification**:
  - `generate_qbo_webhook_signature(payload_bytes, verifier_token)`: Computes base64-encoded HMAC-SHA256 matching Intuit's specification.
  - `verify_qbo_webhook_signature(payload_bytes, signature_header, verifier_token)`: Constant-time digest comparison preventing timing attacks.
- **`WebhookProcessor`**:
  - Unpacks Intuit `eventNotifications` containing `realmId`, `dataChangeEvent`, and entity array (`name`, `id`, `operation`, `lastUpdated`).
  - Idempotency check: verifies `event_id` against `webhook_events` table before processing to prevent replay and duplicate billing actions.
  - Entity Routing:
    - `Payment` (Create/Update): dynamically detects linked invoice(s), pulls latest QBO balance, records payment transaction, and updates invoice state (`PARTIAL` or `PAID`).
    - `Invoice` (Void/Delete): marks invoice as `VOIDED` with zero remaining balance in the ledger.
    - `Invoice` (Update): re-syncs balance and dates.

### `qb_invoicing/ledger.py`
- **`webhook_events` Table**: Tracks processed events (`event_id`, `realm_id`, `event_type`, `entity_name`, `entity_id`, `operation`, `payload`, `processed_at`).
- Added helper methods: `is_webhook_event_processed`, `record_webhook_event`, `void_invoice`, and `get_recent_webhook_events`.

### `qb_invoicing/api.py`
- **FastAPI Web Service**:
  - `POST /api/webhooks/quickbooks`: Intuit Webhook receiver with header validation (`intuit-signature`).
  - `GET /api/metrics`: Live financial KPIs (Total Invoiced, Total Collected, Outstanding, Overdue).
  - `GET /api/invoices`: List and filter invoices.
  - `GET /api/invoices/{identifier}`: Complete invoice detail with linked payment receipts.
  - `POST /api/orders/generate`: Ingest order JSON and generate QBO invoice over REST.
  - `POST /api/invoices/{identifier}/payment`: Record manual payment via REST.
  - `GET /api/invoices/{identifier}/html`: View printable HTML invoice.
  - `GET /`: Interactive Tailwind CSS web dashboard displaying KPI summary cards, invoice list with color-coded status pills, and links to HTML preview documents.

### `qb_invoicing/cli.py`
- Added `serve` command: launches the FastAPI web dashboard on `http://127.0.0.1:8000`.
- Added `simulate-webhook` command: simulates Intuit webhook payloads with valid cryptographic signatures.

---

## 3. Test Suite Verification

- **Total Tests Executed**: 33
- **Tests Passing**: 33 / 33 (100%)
- **Execution Time**: 4.64 seconds
- **New Test Coverage**:
  - `tests/test_webhooks.py`:
    - Signature generation and verification (valid, tampered payload, invalid secret, missing header).
    - End-to-end webhook payment processing updating ledger balance.
    - Event deduplication and replay prevention.
    - Automated invoice voiding via webhook.
  - `tests/test_api.py`:
    - REST metrics and invoice list endpoints.
    - REST order ingestion and invoice generation.
    - REST payment recording and status transition.
    - Webhook endpoint 401 unauthorized on bad signature.
    - Webhook endpoint 200 success on valid signature.
    - Interactive HTML dashboard rendering.
