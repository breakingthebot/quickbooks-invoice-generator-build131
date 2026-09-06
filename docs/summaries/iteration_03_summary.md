# Iteration 3: Automated Dunning Escalation & Accounts Receivable Aging Engine (`v1.2.0`)

## Overview & Objectives
Iteration 3 introduces an enterprise-grade automated dunning and overdue payment escalation workflow to the QuickBooks Online Invoicing platform. The engine categorizes outstanding invoices into standard aging schedule buckets (Current, 1-30 Days, 31-60 Days, 61-90 Days, 90+ Days), automatically determines escalation tiers with tailored notice templates, enforces frequency cooldown periods to prevent spam, tracks notice history in SQLite, and provides both REST API endpoints, web dashboard integration, and CLI commands.

---

## Architectural Additions

### Escalation Tiers & Dunning Schedule
| Days Overdue | Escalation Tier | Severity | Action & Tone |
| :--- | :--- | :--- | :--- |
| `<= 0` | None (Current) | Normal | No action required; not overdue |
| `1 - 14 Days` | Tier 1: Friendly Reminder | Low | Courteous notice of missed due date with invoice summary |
| `15 - 30 Days` | Tier 2: Urgent Notice | Medium | Firm prompt highlighting aging balance and disruption risk |
| `31 - 60 Days` | Tier 3: Final Demand | High | Strong demand with service suspension warning |
| `61+ Days` | Tier 4: Collections Warning | Critical | Formal pre-collections notice prior to external collection referral |

### Frequency Cooldown & Spam Suppression
To prevent spamming clients with daily emails:
- A configurable cooldown period (default: `7 days`, configured via `DUNNING_COOLDOWN_DAYS`) is enforced.
- When an overdue invoice is evaluated, the engine queries `get_last_dunning_notice()`: if a notice was sent within the cooldown window, notice dispatch is suppressed unless overridden with `force=True`.

---

## Key Files Introduced & Modified

### 1. `src/qb_invoicing/dunning.py` (New)
- **`get_escalation_level(days_overdue: int)`**: Maps days overdue to `DunningLevel` (FRIENDLY, URGENT, FINAL_DEMAND, COLLECTIONS).
- **`generate_dunning_content(...)`**: Produces customized plain-text and responsive HTML email templates with dynamic color badges, invoice metadata, payment links, and contact information.
- **`DunningEngine`**:
  - `get_aging_schedule(as_of_date)`: Generates accounts receivable aging schedules.
  - `evaluate_invoice(invoice_id, as_of_date, cooldown_days, force)`: Evaluates single invoice eligibility.
  - `run_dunning_cycle(as_of_date, cooldown_days, force, dry_run)`: Batch evaluates all open invoices and generates or records notices.

### 2. `src/qb_invoicing/models.py` (Enhanced)
- Added `AgingBucket` enum (`Current`, `1-30 Days`, `31-60 Days`, `61-90 Days`, `90+ Days`).
- Added `DunningLevel` enum (1 to 4).
- Added `AgingBucketInvoice` and `AgingScheduleReport` models.
- Added `DunningNoticeRecord` and `DunningBatchResult` models.

### 3. `src/qb_invoicing/ledger.py` (Enhanced)
- Added `dunning_history` table schema with indexes on `invoice_id` and `sent_at`.
- Added `record_dunning_notice()`: Inserts notice audit records.
- Added `get_last_dunning_notice()`: Fetches the most recent notice for cooldown evaluation.
- Added `get_dunning_history()`: Retrieves recent notice history.
- Added `get_aging_report()`: Aggregates open invoices into aging schedule buckets.
- Added `get_invoice()` convenience lookup method.

### 4. `src/qb_invoicing/api.py` (Enhanced)
- `GET /api/dunning/aging-report`: Returns accounts receivable aging schedule JSON.
- `GET /api/dunning/history`: Returns audit log of sent dunning notices.
- `POST /api/dunning/run`: Executes batch dunning escalation cycle.
- `POST /api/dunning/evaluate/{id}`: Evaluates and previews dunning notice for an invoice.
- `GET /api/webhooks/events`: Lists inbound webhook events.
- **Web Dashboard (`GET /`)**: Added Accounts Receivable Aging Schedule card grid, "Run Dunning Escalation" interactive button, and Dunning Notice History log table.

### 5. `src/qb_invoicing/cli.py` (Enhanced)
- `qb-invoicing aging-report [--as-of YYYY-MM-DD]`: Rich table output of aging schedule buckets and detailed open invoice breakdown.
- `qb-invoicing dunning-run [--as-of] [--cooldown-days] [--force] [--dry-run]`: Executes automated dunning cycle.
- `qb-invoicing dunning-history [--limit]`: Displays formatted dunning notice audit log.

### 6. Test Suite Expansion (`tests/test_dunning.py`, `tests/test_api.py`, `tests/test_cli.py`)
- Added 10 new tests across dunning escalation logic, content generation, cooldown suppression, aging schedule bucket grouping, REST API endpoints, and CLI commands.
- Total test count increased from 33 to **43 passing tests**.
