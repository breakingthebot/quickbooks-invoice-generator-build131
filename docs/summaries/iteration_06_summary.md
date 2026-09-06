# Iteration 06: Multi-Gateway Payment Checkout & Stripe / ACH Auto-Settlement Engine

## Executive Summary
Iteration 06 elevates the platform from an invoicing and tracking tool into an active, self-service accounts receivable collection and automated settlement engine. It introduces a multi-gateway payment architecture centered around **Stripe Checkout** and **US ACH Direct Debit (Bank Transfer)**, complete with cryptographic webhook signature verification (`Stripe-Signature` HMAC-SHA256), automatic ledger and QuickBooks Online reconciliation, customer payment portal pages (`/pay/{identifier}`), an offline sandbox checkout simulator (`/pay/checkout/{session_id}`), and dedicated CLI commands.

---

## 1. Architectural Architecture & Data Flow

```
+-----------------------------------------------------------------------------------+
|                           CUSTOMER PAYMENT FLOW                                   |
+-----------------------------------------------------------------------------------+
                                    |
                 +------------------+------------------+
                 |                                     |
        [Hosted Payment Portal]             [Dunning Reminder Email]
         /pay/{qbo_invoice_id}              Embeds Direct Pay Link
                 |                                     |
                 +------------------+------------------+
                                    |
                                    v
                 [Stripe Checkout Session Generated]
                 POST /api/invoices/{id}/checkout-session
                                    |
                 +------------------+------------------+
                 |                                     |
         [Card / Apple/Google Pay]               [US ACH Direct Debit]
                 |                                     |
                 +------------------+------------------+
                                    |
                                    v
               [Customer Authorizes Settlement]
                                    |
                                    v
            [Cryptographic Webhook Notification]
                 POST /api/webhooks/stripe
            Header: Stripe-Signature (HMAC-SHA256)
                                    |
        +---------------------------+---------------------------+
        |                                                       |
        v                                                       v
  [HMAC-SHA256 Signature Valid?]                          [Idempotency Check]
  - Compares t={ts},v1={hash}                             - Checks webhook_events table
  - Enforces 300s timestamp freshness                     - Skips duplicates safely
        |
        v
  [Automated Reconciliation Engine]
  1. Records QBO `Payment` entity via Accounting API v3
  2. Creates `PaymentRecord` in SQLite ledger
  3. Recomputes balance and transitions status (PAID/PARTIAL)
  4. Records event audit log in `webhook_events` table
  5. Redirects customer to /pay/success/{id} receipt
```

---

## 2. Key Components Delivered

### A. Stripe Checkout & Settlement Engine (`src/qb_invoicing/stripe_engine.py`)
- **`create_checkout_session(invoice)`**: Creates session with client reference ID, line items, and payment method options (`card`, `us_bank_account`).
- **`verify_webhook_signature(payload_bytes, sig_header)`**: Validates incoming Stripe webhooks using constant-time `hmac.compare_digest`, extracts timestamp `t` and signature `v1`, and validates timestamp within 300-second freshness tolerance.
- **`generate_signed_webhook_header(payload_bytes)`**: Generates valid test headers for deterministic offline testing and CLI simulations.
- **`process_webhook_event(event_dict, ...)`**: Idempotently auto-settles payment, creates QBO `Payment` object, updates SQLite invoice balance, and audits the transaction.

### B. Hosted Customer Payment Portal (`src/qb_invoicing/api.py`)
- **`GET /pay/{identifier}`**: Responsive customer payment interface displaying invoice summary, current balance, payment channel selector (Card vs. ACH), "Proceed to Stripe Checkout" button, and 1-click test settlement action.
- **`GET /pay/checkout/{session_id}`**: High-fidelity mock Stripe Checkout simulator for zero-friction local testing without requiring active internet tunnels or paid Stripe accounts.
- **`GET /pay/success/{identifier}`**: Emerald confirmation screen presenting payment receipt details, zero balance confirmation, and links to download printable invoices.
- **`POST /api/invoices/{identifier}/checkout-session`**: REST endpoint returning checkout URLs.
- **`POST /api/webhooks/stripe`**: Cryptographically secured webhook ingestion listener.
- **`POST /api/pay/simulate`**: Sandbox simulation endpoint for testing instant customer payments.

### C. CLI Commands (`src/qb_invoicing/cli.py`)
- **`qb-invoicing checkout --invoice <doc_num>`**: Generates checkout sessions directly from the terminal with Rich table formatting.
- **`qb-invoicing simulate-stripe-payment --invoice <doc_num> [--amount] [--method <card|ach>]`**: Generates a cryptographically signed mock Stripe webhook, verifies the signature, and auto-settles the payment into QBO and local ledger.

### D. Automated Dunning Notice Integration (`src/qb_invoicing/dunning.py`)
- Overdue reminder emails now dynamically include direct links to the self-service payment portal (`http://localhost:8000/pay/{qbo_invoice_id}`), enabling immediate customer resolution upon receipt of Friendly, Urgent, or Final Demand notices.

---

## 3. Verification & Testing

All 59 unit and integration tests passed with 100% success:

| Test Module | Coverage | Status |
| :--- | :--- | :---: |
| `tests/test_stripe.py` | Sessions, HMAC Verification, Card/ACH Settlement, Idempotency, API, Portal, CLI | **16 / 16 PASSED** |
| `tests/test_api.py` | FastAPI REST endpoints, Intuit Webhooks, Dunning API, Dashboard | **12 / 12 PASSED** |
| `tests/test_cli.py` | CLI commands (`version`, `preview`, `generate`, `aging-report`, `dunning-run`) | **6 / 6 PASSED** |
| `tests/test_dunning.py` | Escalation tiers, templates, cooldown logic, aging schedule | **5 / 5 PASSED** |
| `tests/test_ledger.py` | SQLite persistence, payment tracking, balance updating, metrics | **3 / 3 PASSED** |
| `tests/test_models.py` | Address mapping, tax/shipping math, validation rules, KPIs | **5 / 5 PASSED** |
| `tests/test_payment_tracker.py` | Payment status determination, sync workflow, manual payments | **2 / 2 PASSED** |
| `tests/test_qbo_client.py` | Customer/Invoice/Payment QBO API v3 mock operations | **3 / 3 PASSED** |
| `tests/test_transformer.py` | Order ingestion, tax calculation, line item transformations | **3 / 3 PASSED** |
| `tests/test_webhooks.py` | Intuit HMAC verification, payment reconciliation, voiding | **4 / 4 PASSED** |
| **Total** | **Full Platform Suite** | **59 / 59 PASSED (100%)** |
