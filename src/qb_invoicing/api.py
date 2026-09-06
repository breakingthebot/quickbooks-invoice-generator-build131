"""
FastAPI REST API & Interactive Web Dashboard for QuickBooks Invoicing.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from qb_invoicing import __version__
from qb_invoicing.config import Settings, settings
from qb_invoicing.dunning import DunningEngine
from qb_invoicing.ledger import LedgerRepository
from qb_invoicing.models import (
    AgingScheduleReport,
    DunningBatchResult,
    DunningNoticeRecord,
    FinancialMetrics,
    InvoiceRecord,
    OrderData,
    PaymentRecord,
    PaymentStatus,
)
from qb_invoicing.payment_tracker import PaymentStatusTracker
from qb_invoicing.qbo_client import QuickBooksClient
from qb_invoicing.renderer import InvoiceRenderer
from qb_invoicing.transformer import OrderTransformer
from qb_invoicing.webhooks import WebhookProcessor


class ManualPaymentRequest(BaseModel):
    amount: float
    payment_method: str = "CreditCard"
    reference_num: Optional[str] = None


class DunningRunRequest(BaseModel):
    as_of_date: Optional[str] = None
    cooldown_days: Optional[int] = None
    force: bool = False
    dry_run: bool = False


def create_app(cfg: Optional[Settings] = None) -> FastAPI:
    """Application factory for FastAPI service."""
    app_config = cfg or Settings.load()
    app = FastAPI(
        title="QuickBooks Online Invoice Generator API",
        version=__version__,
        description="REST API and Webhook Engine for QuickBooks Online Invoicing and Payment Tracking",
    )

    # Enable CORS for Vercel, localhost, and mobile clients
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    client = QuickBooksClient(app_config)
    ledger = LedgerRepository(app_config.database_path)
    tracker = PaymentStatusTracker(client, ledger)
    transformer = OrderTransformer(default_terms_days=app_config.default_payment_terms_days)
    webhook_processor = WebhookProcessor(client, ledger, tracker)
    dunning_engine = DunningEngine(ledger=ledger, settings=app_config)

    # ========================================================================
    # Webhooks Endpoints
    # ========================================================================

    @app.post("/api/webhooks/quickbooks", tags=["Webhooks"])
    async def intuit_webhook_receiver(
        request: Request,
        intuit_signature: Optional[str] = Header(None, alias="intuit-signature"),
    ):
        """
        Receives and cryptographically verifies QuickBooks Online webhook events.
        Automatically reconciles payment creation and invoice status changes.
        """
        body_bytes = await request.body()
        try:
            result = webhook_processor.process_payload(
                payload_bytes=body_bytes,
                signature=intuit_signature,
                verifier_token=app_config.webhook_verifier_token,
            )
            return JSONResponse(status_code=status.HTTP_200_OK, content=result)
        except PermissionError as pe:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(pe))
        except ValueError as ve:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Webhook error: {e}")

    @app.get("/api/webhooks/events", tags=["Webhooks"])
    def list_webhook_events(limit: int = Query(25, ge=1, le=100)):
        """Retrieve recent webhook events received and processed."""
        return ledger.get_recent_webhook_events(limit=limit)

    # ========================================================================
    # Dunning & Aging Schedule Endpoints
    # ========================================================================

    @app.get("/api/dunning/aging-report", response_model=AgingScheduleReport, tags=["Dunning & Aging"])
    def get_aging_report(
        as_of_date: Optional[str] = Query(None, description="Reference evaluation date (YYYY-MM-DD)"),
    ):
        """Calculate accounts receivable aging schedule with buckets (Current, 1-30d, 31-60d, 61-90d, 90+d)."""
        return dunning_engine.get_aging_schedule(as_of_date=as_of_date)

    @app.get("/api/dunning/history", response_model=List[DunningNoticeRecord], tags=["Dunning & Aging"])
    def get_dunning_history(limit: int = Query(50, ge=1, le=200)):
        """Retrieve historical dunning reminder notices dispatched or simulated."""
        return ledger.get_dunning_history(limit=limit)

    @app.post("/api/dunning/run", response_model=DunningBatchResult, tags=["Dunning & Aging"])
    def run_dunning_cycle(req: Optional[DunningRunRequest] = None):
        """
        Execute automated overdue escalation across all open invoices.
        Evaluates due dates, applies cooldown suppression, and generates notices.
        """
        r = req or DunningRunRequest()
        result = dunning_engine.run_dunning_cycle(
            as_of_date=r.as_of_date,
            cooldown_days=r.cooldown_days,
            force=r.force,
            dry_run=r.dry_run,
        )
        return result

    @app.post("/api/dunning/evaluate/{identifier}", tags=["Dunning & Aging"])
    def evaluate_single_dunning(
        identifier: str,
        force: bool = Query(False),
        as_of_date: Optional[str] = Query(None),
    ):
        """Evaluate a specific invoice and preview dunning notice if overdue."""
        inv = ledger.get_invoice_by_id(identifier) or ledger.get_invoice_by_doc_number(identifier)
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        notice = dunning_engine.evaluate_invoice(inv.qbo_invoice_id, as_of_date=as_of_date, force=force)
        if not notice:
            return {"status": "SKIPPED", "message": "Invoice is either not overdue, paid, or currently in cooldown period."}
        return {"status": "ELIGIBLE", "notice": notice.model_dump()}

    # ========================================================================
    # REST API Endpoints
    # ========================================================================

    @app.get("/api/metrics", response_model=FinancialMetrics, tags=["Metrics"])
    def get_metrics():
        """Get live financial KPIs and status counts."""
        return ledger.get_metrics()

    @app.get("/api/invoices", tags=["Invoices"])
    def list_invoices(
        status: Optional[str] = Query(None, description="Filter by status (PENDING, PAID, etc.)"),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        """List tracked invoices from the database."""
        filter_status = PaymentStatus(status.upper()) if status else None
        invoices = ledger.list_invoices(status=filter_status, limit=limit, offset=offset)
        return [inv.model_dump() for inv in invoices]

    @app.get("/api/invoices/{identifier}", tags=["Invoices"])
    def get_invoice_detail(identifier: str):
        """Retrieve single invoice with payment transactions."""
        inv = (
            ledger.get_invoice_by_id(identifier)
            or ledger.get_invoice_by_doc_number(identifier)
            or ledger.get_invoice_by_order_id(identifier)
        )
        if not inv:
            raise HTTPException(status_code=404, detail=f"Invoice '{identifier}' not found")

        # Sync live state from QBO
        synced = tracker.sync_invoice_status(inv.qbo_invoice_id) or inv
        payments = ledger.get_payments_for_invoice(synced.qbo_invoice_id)
        return {
            "invoice": synced.model_dump(),
            "payments": [p.model_dump() for p in payments],
        }

    @app.post("/api/orders/generate", tags=["Invoices"])
    def generate_invoice_from_order(order_payload: Dict[str, Any]):
        """Ingest order data and generate QuickBooks Online invoice."""
        try:
            order = transformer.parse_order(order_payload)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid order payload: {e}")

        ledger.save_order(order)
        qbo_customer = client.get_or_create_customer(order.customer.name, order.customer.email, order.customer.company_name)
        qbo_payload = transformer.transform_to_qbo_invoice(order, qbo_customer_id=str(qbo_customer.get("Id", "1")))
        created = client.create_invoice(qbo_payload)

        qbo_id = str(created.get("Id"))
        doc_num = str(created.get("DocNumber", qbo_payload.DocNumber))
        total_amt = Decimal(str(created.get("TotalAmt", order.computed_total)))
        bal = Decimal(str(created.get("Balance", total_amt)))

        inv_record = InvoiceRecord(
            qbo_invoice_id=qbo_id,
            order_id=order.order_id,
            doc_number=doc_num,
            customer_name=order.customer.name,
            customer_email=order.customer.email,
            txn_date=qbo_payload.TxnDate,
            due_date=qbo_payload.DueDate,
            total_amount=total_amt,
            balance_due=bal,
            payment_status=PaymentStatus.PENDING if bal > 0 else PaymentStatus.PAID,
            currency=order.currency,
            raw_payload=qbo_payload.model_dump_json(),
            raw_response=json.dumps(created),
        )
        ledger.save_invoice(inv_record)
        return inv_record.model_dump()

    @app.post("/api/invoices/{identifier}/payment", tags=["Payments"])
    def record_invoice_payment(identifier: str, req: ManualPaymentRequest):
        """Record manual payment against an invoice."""
        inv = ledger.get_invoice_by_id(identifier) or ledger.get_invoice_by_doc_number(identifier)
        if not inv:
            raise HTTPException(status_code=404, detail=f"Invoice '{identifier}' not found")

        try:
            payment = tracker.record_manual_payment(
                qbo_invoice_id=inv.qbo_invoice_id,
                amount=Decimal(str(req.amount)),
                payment_method=req.payment_method,
                reference_num=req.reference_num,
            )
            updated = ledger.get_invoice_by_id(inv.qbo_invoice_id)
            return {
                "status": "SUCCESS",
                "payment": payment.model_dump(),
                "invoice": updated.model_dump() if updated else None,
            }
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))

    @app.get("/api/invoices/{identifier}/html", response_class=HTMLResponse, tags=["Invoices"])
    def preview_invoice_html(identifier: str):
        """Render printable HTML invoice."""
        inv = ledger.get_invoice_by_id(identifier) or ledger.get_invoice_by_doc_number(identifier)
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        return InvoiceRenderer.render_html(inv)

    # ========================================================================
    # Interactive Web Dashboard
    # ========================================================================

    @app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
    def web_dashboard():
        """Interactive Tailwind CSS dashboard."""
        metrics = ledger.get_metrics()
        invoices = ledger.list_invoices(limit=50)
        aging = dunning_engine.get_aging_schedule()
        dunning_history = ledger.get_dunning_history(limit=10)
        webhook_events = ledger.get_recent_webhook_events(limit=5)

        rows_html = ""
        for inv in invoices:
            badge_color = {
                "PAID": "bg-emerald-100 text-emerald-800 border-emerald-300",
                "PENDING": "bg-amber-100 text-amber-800 border-amber-300",
                "PARTIAL": "bg-blue-100 text-blue-800 border-blue-300",
                "OVERDUE": "bg-rose-100 text-rose-800 border-rose-300",
                "VOIDED": "bg-gray-100 text-gray-800 border-gray-300",
            }.get(inv.payment_status.value, "bg-gray-100 text-gray-800 border-gray-300")

            rows_html += f"""
            <tr class="hover:bg-slate-50 transition border-b border-slate-100">
                <td class="py-3 px-4 font-mono font-semibold text-indigo-600"><a href="/api/invoices/{inv.doc_number}/html" target="_blank" class="hover:underline">{inv.doc_number}</a></td>
                <td class="py-3 px-4 text-xs text-slate-500 font-mono">{inv.qbo_invoice_id}</td>
                <td class="py-3 px-4 text-slate-700">{inv.customer_name}</td>
                <td class="py-3 px-4 text-slate-500 text-sm">{inv.txn_date}</td>
                <td class="py-3 px-4 text-slate-500 text-sm">{inv.due_date or 'Upon Receipt'}</td>
                <td class="py-3 px-4 text-right font-medium text-slate-900">${inv.total_amount:.2f}</td>
                <td class="py-3 px-4 text-right font-bold {'text-emerald-600' if inv.balance_due == 0 else 'text-amber-600'}">${inv.balance_due:.2f}</td>
                <td class="py-3 px-4 text-center">
                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold border {badge_color}">{inv.payment_status.value}</span>
                </td>
            </tr>
            """

        if not invoices:
            rows_html = """<tr><td colspan="8" class="text-center py-12 text-slate-400">No invoices generated yet. Use the CLI or API to create one!</td></tr>"""

        # Dunning rows
        dunning_rows = ""
        for d in dunning_history:
            level_badge = {
                1: "bg-blue-100 text-blue-800 border-blue-200",
                2: "bg-amber-100 text-amber-800 border-amber-200",
                3: "bg-orange-100 text-orange-800 border-orange-200",
                4: "bg-rose-100 text-rose-800 border-rose-200",
            }.get(d.escalation_level, "bg-gray-100 text-gray-800 border-gray-200")

            dunning_rows += f"""
            <tr class="hover:bg-slate-50 transition border-b border-slate-100 text-sm">
                <td class="py-2.5 px-4 font-mono font-medium text-slate-700">{d.doc_number}</td>
                <td class="py-2.5 px-4 text-slate-700">{d.customer_name}</td>
                <td class="py-2.5 px-4"><span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold border {level_badge}">Tier {d.escalation_level}: {d.level_name}</span></td>
                <td class="py-2.5 px-4 text-slate-600">{d.days_overdue} days</td>
                <td class="py-2.5 px-4 font-medium text-slate-800">${d.balance_due:.2f}</td>
                <td class="py-2.5 px-4 text-xs text-slate-400 font-mono">{d.sent_at.strftime('%Y-%m-%d %H:%M')}</td>
                <td class="py-2.5 px-4"><span class="text-xs font-bold text-emerald-600">{d.status}</span></td>
            </tr>
            """

        if not dunning_history:
            dunning_rows = """<tr><td colspan="7" class="text-center py-8 text-slate-400">No dunning notices dispatched yet. Run a dunning cycle to evaluate overdue accounts.</td></tr>"""

        # Webhook rows
        webhook_rows = ""
        for w in webhook_events:
            webhook_rows += f"""
            <tr class="hover:bg-slate-50 transition border-b border-slate-100 text-sm">
                <td class="py-2 px-3 font-mono text-xs text-slate-600">{w['event_id'][:12]}...</td>
                <td class="py-2 px-3 font-medium text-indigo-600">{w['entity_name']}</td>
                <td class="py-2 px-3 text-slate-700">{w['operation']}</td>
                <td class="py-2 px-3 text-xs text-slate-500 font-mono">{w['entity_id']}</td>
                <td class="py-2 px-3 text-xs text-slate-400 font-mono">{w['processed_at'][:19]}</td>
            </tr>
            """
        if not webhook_events:
            webhook_rows = """<tr><td colspan="5" class="text-center py-6 text-slate-400">No webhook events received yet.</td></tr>"""

        dashboard_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QuickBooks Online Invoicing &amp; Dunning Portal</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-50 text-slate-800 antialiased min-h-screen">
    <header class="bg-slate-900 text-white shadow-md">
        <div class="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
            <div class="flex items-center space-x-3">
                <div class="w-8 h-8 rounded bg-emerald-500 flex items-center justify-center font-bold text-white shadow">Q</div>
                <div>
                    <h1 class="text-lg font-bold tracking-tight">QuickBooks Online Invoicing Platform</h1>
                    <p class="text-xs text-slate-400">Accounting API v3 &bull; Webhook Sync &bull; Automated Dunning Engine (v{__version__})</p>
                </div>
            </div>
            <div class="flex items-center space-x-3">
                <span class="inline-flex items-center px-2.5 py-1 rounded text-xs font-medium bg-emerald-950 text-emerald-400 border border-emerald-800">
                    <span class="w-2 h-2 mr-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                    API Mode: {'Mock Sandbox' if app_config.use_mock else 'Live Intuit'}
                </span>
                <a href="/docs" target="_blank" class="text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded border border-slate-700 transition">API Docs (Swagger)</a>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-8">
        <!-- KPI Metrics Grid -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
            <div class="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
                <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Total Invoiced</div>
                <div class="text-2xl font-bold text-slate-900 mt-2">${metrics.total_invoiced_amount:.2f}</div>
                <div class="text-xs text-slate-500 mt-1">{metrics.total_invoices} invoices tracked</div>
            </div>
            <div class="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
                <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Total Collected</div>
                <div class="text-2xl font-bold text-emerald-600 mt-2">${metrics.total_collected_amount:.2f}</div>
                <div class="text-xs text-emerald-600 font-medium mt-1">{metrics.paid_invoices_count} fully paid</div>
            </div>
            <div class="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
                <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Outstanding Balance</div>
                <div class="text-2xl font-bold text-amber-600 mt-2">${metrics.total_outstanding_balance:.2f}</div>
                <div class="text-xs text-amber-600 font-medium mt-1">{metrics.partial_invoices_count + metrics.pending_invoices_count} open balance</div>
            </div>
            <div class="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
                <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Overdue Accounts</div>
                <div class="text-2xl font-bold text-rose-600 mt-2">{metrics.overdue_invoices_count}</div>
                <div class="text-xs text-rose-500 mt-1">Requires dunning escalation</div>
            </div>
        </div>

        <!-- Accounts Receivable Aging Schedule Card -->
        <div class="bg-white rounded-xl shadow-sm border border-slate-200 mb-8 p-6">
            <div class="flex flex-col md:flex-row md:items-center justify-between pb-4 border-b border-slate-100 gap-4">
                <div>
                    <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
                        <span>Accounts Receivable Aging Schedule</span>
                        <span class="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-600 font-normal">As of: {aging.as_of_date}</span>
                    </h2>
                    <p class="text-xs text-slate-500">Categorized receivables into aging buckets with automated escalation tiers</p>
                </div>
                <div class="flex items-center space-x-3">
                    <button onclick="triggerDunningCycle()" id="dunningBtn" class="inline-flex items-center px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold shadow transition cursor-pointer">
                        <svg class="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
                        Run Dunning Escalation
                    </button>
                </div>
            </div>

            <!-- Aging Buckets Grid -->
            <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mt-5 text-center">
                <div class="p-4 rounded-lg bg-emerald-50 border border-emerald-100">
                    <div class="text-xs font-semibold text-emerald-800 uppercase tracking-wide">Current</div>
                    <div class="text-xl font-bold text-emerald-900 mt-1">${aging.current_amount:.2f}</div>
                    <div class="text-xs text-emerald-600 mt-0.5">Not yet due</div>
                </div>
                <div class="p-4 rounded-lg bg-blue-50 border border-blue-100">
                    <div class="text-xs font-semibold text-blue-800 uppercase tracking-wide">1-30 Days</div>
                    <div class="text-xl font-bold text-blue-900 mt-1">${aging.days_1_30_amount:.2f}</div>
                    <div class="text-xs text-blue-600 mt-0.5">Friendly Reminder</div>
                </div>
                <div class="p-4 rounded-lg bg-amber-50 border border-amber-100">
                    <div class="text-xs font-semibold text-amber-800 uppercase tracking-wide">31-60 Days</div>
                    <div class="text-xl font-bold text-amber-900 mt-1">${aging.days_31_60_amount:.2f}</div>
                    <div class="text-xs text-amber-600 mt-0.5">Urgent Notice</div>
                </div>
                <div class="p-4 rounded-lg bg-orange-50 border border-orange-100">
                    <div class="text-xs font-semibold text-orange-800 uppercase tracking-wide">61-90 Days</div>
                    <div class="text-xl font-bold text-orange-900 mt-1">${aging.days_61_90_amount:.2f}</div>
                    <div class="text-xs text-orange-600 mt-0.5">Final Demand</div>
                </div>
                <div class="p-4 rounded-lg bg-rose-50 border border-rose-100">
                    <div class="text-xs font-semibold text-rose-800 uppercase tracking-wide">90+ Days</div>
                    <div class="text-xl font-bold text-rose-900 mt-1">${aging.days_over_90_amount:.2f}</div>
                    <div class="text-xs text-rose-600 mt-0.5">Collections Warning</div>
                </div>
            </div>
        </div>

        <!-- Invoices Table Card -->
        <div class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden mb-8">
            <div class="p-5 border-b border-slate-100 flex items-center justify-between">
                <div>
                    <h2 class="text-base font-bold text-slate-900">Tracked Invoices &amp; Ledger Status</h2>
                    <p class="text-xs text-slate-500">Live synced with QuickBooks Online Accounting API v3</p>
                </div>
                <div class="text-xs text-slate-400">
                    Webhook receiver active at: <code class="bg-slate-100 px-2 py-0.5 rounded text-indigo-600 font-mono">/api/webhooks/quickbooks</code>
                </div>
            </div>
            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider font-semibold border-b border-slate-200">
                            <th class="py-3 px-4">Doc #</th>
                            <th class="py-3 px-4">QBO ID</th>
                            <th class="py-3 px-4">Customer</th>
                            <th class="py-3 px-4">Txn Date</th>
                            <th class="py-3 px-4">Due Date</th>
                            <th class="py-3 px-4 text-right">Total</th>
                            <th class="py-3 px-4 text-right">Balance</th>
                            <th class="py-3 px-4 text-center">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Dunning Notices & Webhook Events Split -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <!-- Dunning Notices History -->
            <div class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                <div class="p-5 border-b border-slate-100">
                    <h3 class="text-base font-bold text-slate-900">Dunning Notice Escalation History</h3>
                    <p class="text-xs text-slate-500">Audit trail of payment reminder notices dispatched</p>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider font-semibold border-b border-slate-200">
                                <th class="py-2.5 px-4">Doc #</th>
                                <th class="py-2.5 px-4">Customer</th>
                                <th class="py-2.5 px-4">Escalation Tier</th>
                                <th class="py-2.5 px-4">Overdue</th>
                                <th class="py-2.5 px-4">Balance</th>
                                <th class="py-2.5 px-4">Dispatched</th>
                                <th class="py-2.5 px-4">Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {dunning_rows}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Inbound Webhook Event Stream -->
            <div class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                <div class="p-5 border-b border-slate-100">
                    <h3 class="text-base font-bold text-slate-900">QuickBooks Webhook Event Stream</h3>
                    <p class="text-xs text-slate-500">Cryptographically verified inbound Intuit push notifications</p>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider font-semibold border-b border-slate-200">
                                <th class="py-2 px-3">Event ID</th>
                                <th class="py-2 px-3">Entity</th>
                                <th class="py-2 px-3">Operation</th>
                                <th class="py-2 px-3">Target ID</th>
                                <th class="py-2 px-3">Timestamp</th>
                            </tr>
                        </thead>
                        <tbody>
                            {webhook_rows}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </main>

    <script>
        async function triggerDunningCycle() {{
            const btn = document.getElementById('dunningBtn');
            btn.disabled = true;
            btn.innerText = 'Evaluating Invoices...';
            try {{
                const res = await fetch('/api/dunning/run', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{force: false}})
                }});
                const data = await res.json();
                alert('Dunning Cycle Completed!\\nEvaluated: ' + data.evaluated_count + ' open invoices\\nNotices Dispatched: ' + data.notices_sent_count + '\\nSkipped (Cooldown): ' + data.skipped_cooldown_count);
                window.location.reload();
            }} catch (err) {{
                alert('Error executing dunning cycle: ' + err);
            }} finally {{
                btn.disabled = false;
                btn.innerText = 'Run Dunning Escalation';
            }}
        }}
    </script>
</body>
</html>"""
        return dashboard_html

    return app


# Default app instance
app = create_app()

