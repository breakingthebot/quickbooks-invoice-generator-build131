# Iteration 07: Vector PDF Generation with Instant QR Payment Codes & Email Dispatch Engine

## Executive Summary
Iteration 07 expands the QuickBooks Online Invoicing platform with automated, print- and audit-compliant **Vector PDF Invoice Generation**, dynamic **Mobile-Scannable Instant Payment QR Codes**, and an **Enterprise Email Dispatch Engine** supporting both live SMTP transports and offline sandbox simulations. Customers receiving desktop or paper invoices can scan the embedded QR code with their mobile cameras to immediately launch the hosted payment portal (`/pay/{qbo_invoice_id}`) and settle balances via Apple Pay, Google Pay, Credit Card, or ACH bank debit.

---

## 1. System Architecture & Data Flow

```
+-----------------------------------------------------------------------------------+
|                        PDF & EMAIL DISPATCH WORKFLOW                              |
+-----------------------------------------------------------------------------------+
                                    |
            +-----------------------+-----------------------+
            |                                               |
     [REST API Request]                             [CLI Execution]
  GET  /api/invoices/{id}/pdf                  qb-invoicing export-pdf
  POST /api/invoices/{id}/send-email           qb-invoicing send-invoice
  GET  /api/invoices/{id}/qr                                |
            |                                               |
            +-----------------------+-----------------------+
                                    |
                                    v
                 [InvoicePDFGenerator (ReportLab 5.0)]
                 1. Extracts Line Items & Customer Billing Address
                 2. Calculates Subtotal, Tax %, Shipping & Balance
                 3. Calls `generate_payment_qr(portal_url)`
                 4. Renders Vector Layout: Header, Grid, Table, Totals, QR
                 5. Produces Binary PDF Stream (%PDF-1.4+)
                                    |
            +-----------------------+-----------------------+
            |                                               |
            v                                               v
    [Streaming Download]                         [InvoiceMailer Engine]
    application/pdf header                       1. Assembles multipart/mixed MIME
    Content-Disposition: inline                  2. Attaches PDF (Invoice_{num}.pdf)
                                                 3. Renders responsive HTML & text
                                                            |
                                    +-----------------------+-----------------------+
                                    |                                               |
                                    v                                               v
                             [Mock Sandbox]                                   [Live SMTP]
                           MAIL_USE_MOCK=true                             MAIL_USE_MOCK=false
                           Validates MIME &                               Connects to host:port
                           skips network sockets                          STARTTLS & AUTH
                                    |                                               |
                                    +-----------------------+-----------------------+
                                                            |
                                                            v
                                            [SQLite Ledger Audit Trail]
                                            Table: `email_dispatches`
                                            Records: id, recipient, sent_at,
                                            status (SIMULATED/SENT), attachment
```

---

## 2. Key Components Delivered

### A. Vector PDF Invoice Generator (`src/qb_invoicing/pdf_generator.py`)
- **ReportLab Platypus Engine**: Built using `SimpleDocTemplate`, `Table`, `KeepTogether`, `HRFlowable`, and custom `ParagraphStyle` typography.
- **Itemized Lines & Financial Breakdown**:
  - Dynamically extracts items, quantities, rates, and tax statuses from `OrderData` or `InvoiceRecord.raw_payload`.
  - Displays alternating row striping with navy table headers (`#1E3A8A`).
  - Calculates subtotal, tax amount, shipping fee, total amount, payments applied, and prominent colored balance due badge (red for overdue, navy for normal).
- **Branding & Metadata**: Incorporates company name, contact information, customer billing address, payment terms (Net 30), transaction date, and payment status badges (`PAID`, `PARTIAL`, `PENDING`, `OVERDUE`, `VOIDED`).
- **Filesystem & In-Memory Operations**:
  - `generate_pdf_bytes(invoice, payment_url, order) -> bytes`: Streaming byte generator for REST endpoints and email attachments.
  - `save_pdf(invoice, output_path, payment_url, order) -> Path`: Exports physical PDF files to `storage/exports/Invoice_{doc_number}.pdf`.

### B. Mobile-Scannable Payment QR Codes (`src/qb_invoicing/pdf_generator.py`)
- **Pure-Vector Matrix Generation**: Built with `qrcode` and `Pillow` using error correction level `M` and configurable box sizing.
- **Embedded Directly on Invoices**: Positioned alongside the totals table in a dedicated scan-to-pay block:
  - *"Scan with your smartphone camera to pay immediately via Credit Card, ACH, Apple Pay, or Google Pay."*
  - Automatically targets `{payment_portal_url}/pay/{qbo_invoice_id}`.
- **Standalone Image Endpoint**: `GET /api/invoices/{identifier}/qr` generates real-time PNG QR codes for web portals, mobile apps, and third-party dashboards.

### C. Invoice Email Dispatch Engine (`src/qb_invoicing/mailer.py`)
- **MIME Multipart Message Composer**:
  - Constructs `multipart/mixed` container holding `multipart/alternative` body (`text/plain` fallback and responsive HTML template) and vector `application/pdf` attachment.
  - Generates professional email copy with customer greetings, statement summary, and prominent "Pay Online Now" button.
- **Dual-Mode Transport**:
  - **Live SMTP**: Connects to `SMTP_HOST:SMTP_PORT` with optional STARTTLS (`SMTP_USE_TLS=true`) and authentication (`SMTP_USER`, `SMTP_PASSWORD`).
  - **Sandbox Mock Mode (`MAIL_USE_MOCK=true`)**: Verifies MIME structure and attachment integrity without requiring an external mail server.
- **Persistent Audit Logging**:
  - Introduces `email_dispatches` table in SQLite repository.
  - Records recipient, subject, timestamp, status (`SIMULATED`, `SENT`, `FAILED`), and error details.
  - Exposed via `LedgerRepository.get_email_dispatches(invoice_id)`.

### D. REST API Endpoints (`src/qb_invoicing/api.py`)
- `GET /api/invoices/{identifier}/pdf`: Streams binary PDF document with inline attachment header.
- `GET /api/invoices/{identifier}/qr`: Streams binary PNG payment QR code.
- `POST /api/invoices/{identifier}/send-email`: Dispatches email with vector PDF attachment (accepts optional custom recipient, subject, or message body).
- `GET /api/invoices/{identifier}/dispatches`: Retrieves chronological email dispatch history.

### E. Portal & Dashboard UI Enhancements
- **Hosted Payment Portal (`/pay/{identifier}`)**:
  - Embedded real-time QR code display with "Scan QR Code to Pay on Mobile" banner.
  - Direct "Download PDF" button opening vector PDF invoice.
  - One-click "Email PDF" dispatch action with user feedback.
- **Interactive Web Dashboard (`/`)**:
  - Added "PDF" and "Email" action buttons to every row in the invoices table.
  - Asynchronous dispatch handler with confirmation prompt and audit feedback.

### F. Terminal CLI Suite (`src/qb_invoicing/cli.py`)
- `qb-invoicing export-pdf --invoice <doc_num/id> [--output <path>] [--portal-url <url>]`: Renders and writes vector PDF to disk with full Rich table summary.
- `qb-invoicing send-invoice --invoice <doc_num/id> [--to <email>] [--subject <str>] [--mock/--no-mock]`: Assembles and dispatches email with attached PDF, printing dispatch audit records.

---

## 3. Verification & Test Coverage

All 80 unit and integration tests across the entire application suite pass with 100% success rate:
- `tests/test_pdf_mailer.py` (21 new tests):
  - QR code PNG signature and scaling validation.
  - PDF generation and vector structure across all payment statuses (`PAID`, `PARTIAL`, `PENDING`, `OVERDUE`, `VOIDED`).
  - Line item extraction from `OrderData` and `raw_payload`.
  - Filesystem export and binary integrity checks.
  - Mock sandbox email dispatch and SQLite ledger auditing.
  - Live SMTP failure error handling and exception logging.
  - REST endpoints (`/pdf`, `/qr`, `/send-email`, `/dispatches`).
  - Hosted portal and web dashboard template integration.
  - CLI commands (`export-pdf`, `send-invoice`).
- Total test count: **80 passed** in `tests/`.
