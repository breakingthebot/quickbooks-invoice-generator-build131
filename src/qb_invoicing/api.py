"""
FastAPI REST API & Interactive Web Dashboard for QuickBooks Invoicing.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from qb_invoicing import __version__
from qb_invoicing.config import Settings, settings
from qb_invoicing.dunning import DunningEngine
from qb_invoicing.ledger import LedgerRepository
from qb_invoicing.mailer import InvoiceMailer
from qb_invoicing.models import (
    AgingScheduleReport,
    DunningBatchResult,
    DunningNoticeRecord,
    EmailDispatchRecord,
    FinancialMetrics,
    InvoiceRecord,
    OrderData,
    PaymentRecord,
    PaymentStatus,
    StripeCheckoutSession,
    StripePaymentIntentResult,
)
from qb_invoicing.payment_tracker import PaymentStatusTracker
from qb_invoicing.pdf_generator import InvoicePDFGenerator, generate_payment_qr
from qb_invoicing.qbo_client import QuickBooksClient
from qb_invoicing.renderer import InvoiceRenderer
from qb_invoicing.stripe_engine import StripeCheckoutEngine
from qb_invoicing.transformer import OrderTransformer
from qb_invoicing.webhooks import WebhookProcessor


class ManualPaymentRequest(BaseModel):
    amount: float
    payment_method: str = "CreditCard"
    reference_num: Optional[str] = None


class SendEmailRequest(BaseModel):
    recipient_email: Optional[str] = None
    subject: Optional[str] = None
    text_body: Optional[str] = None
    html_body: Optional[str] = None


class StripeSimulateRequest(BaseModel):
    invoice_id: str
    amount: Optional[float] = None
    payment_method: Optional[str] = "CreditCard"


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
    stripe_engine = StripeCheckoutEngine(
        api_key=app_config.stripe_api_key,
        webhook_secret=app_config.stripe_webhook_secret,
        use_mock=app_config.stripe_use_mock,
    )
    pdf_generator = InvoicePDFGenerator(app_config)
    mailer = InvoiceMailer(settings=app_config, ledger=ledger, pdf_generator=pdf_generator)

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
    # Stripe Multi-Gateway Payment Checkout Endpoints
    # ========================================================================

    @app.post("/api/invoices/{identifier}/checkout-session", response_model=StripeCheckoutSession, tags=["Stripe Checkout"])
    def create_stripe_checkout_session(
        identifier: str,
        success_url: Optional[str] = Query(None),
        cancel_url: Optional[str] = Query(None),
    ):
        """
        Create a customer-facing Stripe Checkout Session for an open invoice.
        Supports Credit Cards, Apple Pay, Google Pay, and US Bank Account (ACH).
        """
        inv = (
            ledger.get_invoice_by_id(identifier)
            or ledger.get_invoice_by_doc_number(identifier)
            or ledger.get_invoice_by_order_id(identifier)
        )
        if not inv:
            raise HTTPException(status_code=404, detail=f"Invoice '{identifier}' not found")

        session = stripe_engine.create_checkout_session(
            invoice=inv,
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return session

    @app.post("/api/webhooks/stripe", tags=["Stripe Checkout"])
    async def stripe_webhook_receiver(
        request: Request,
        stripe_signature: Optional[str] = Header(None, alias="stripe-signature"),
    ):
        """
        Cryptographically verified Stripe Webhook receiver.
        Validates HMAC-SHA256 signature and auto-settles payment into QuickBooks Online and SQLite ledger.
        """
        body_bytes = await request.body()
        if not stripe_signature:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing stripe-signature header")

        if not stripe_engine.verify_webhook_signature(body_bytes, stripe_signature):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Stripe webhook cryptographic signature")

        try:
            event_dict = json.loads(body_bytes.decode("utf-8"))
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid JSON payload: {e}")

        result = stripe_engine.process_webhook_event(
            event_dict=event_dict,
            ledger=ledger,
            payment_tracker=tracker,
            qbo_client=client,
        )
        return JSONResponse(status_code=status.HTTP_200_OK, content=result.model_dump(mode="json"))

    @app.post("/api/pay/simulate", tags=["Stripe Checkout"])
    def simulate_stripe_payment_endpoint(req: StripeSimulateRequest):
        """
        Simulate an incoming Stripe payment webhook and settlement for an invoice.
        Useful for testing, interactive UI checkout, and instant ledger reconciliation.
        """
        inv = (
            ledger.get_invoice_by_id(req.invoice_id)
            or ledger.get_invoice_by_doc_number(req.invoice_id)
            or ledger.get_invoice_by_order_id(req.invoice_id)
        )
        if not inv:
            raise HTTPException(status_code=404, detail=f"Invoice '{req.invoice_id}' not found")

        pay_amount = Decimal(str(req.amount)) if req.amount is not None else inv.balance_due
        if pay_amount <= Decimal("0.00"):
            pay_amount = inv.total_amount

        cents = int(pay_amount * 100)
        pm_type = "us_bank_account" if (req.payment_method or "").upper() == "ACH" else "card"

        mock_event = {
            "id": f"evt_sim_{uuid4().hex[:12]}",
            "object": "event",
            "type": "checkout.session.completed",
            "created": int(time.time()),
            "data": {
                "object": {
                    "id": f"cs_sim_{uuid4().hex[:16]}",
                    "payment_intent": f"pi_sim_{uuid4().hex[:16]}",
                    "amount_total": cents,
                    "currency": inv.currency.lower(),
                    "payment_status": "paid",
                    "payment_method_types": [pm_type],
                    "metadata": {
                        "qbo_invoice_id": inv.qbo_invoice_id,
                        "doc_number": inv.doc_number,
                    },
                }
            },
        }

        result = stripe_engine.process_webhook_event(
            event_dict=mock_event,
            ledger=ledger,
            payment_tracker=tracker,
            qbo_client=client,
        )
        return result.model_dump(mode="json")

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

    @app.get("/api/invoices/{identifier}/pdf", tags=["Invoices"])
    def download_invoice_pdf(identifier: str):
        """Stream audit-compliant vector PDF invoice with embedded payment QR code."""
        inv = (
            ledger.get_invoice_by_id(identifier)
            or ledger.get_invoice_by_doc_number(identifier)
            or ledger.get_invoice_by_order_id(identifier)
        )
        if not inv:
            raise HTTPException(status_code=404, detail=f"Invoice '{identifier}' not found")

        order = None
        if inv.order_id:
            order = ledger.get_order(inv.order_id)

        pdf_bytes = pdf_generator.generate_pdf_bytes(inv, order=order)
        filename = f"Invoice_{inv.doc_number}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
                "Content-Type": "application/pdf",
            },
        )

    @app.get("/api/invoices/{identifier}/qr", tags=["Invoices"])
    def get_invoice_qr(identifier: str):
        """Generate dynamic, real-time payment QR code image (PNG) for mobile checkout."""
        inv = (
            ledger.get_invoice_by_id(identifier)
            or ledger.get_invoice_by_doc_number(identifier)
            or ledger.get_invoice_by_order_id(identifier)
        )
        if not inv:
            raise HTTPException(status_code=404, detail=f"Invoice '{identifier}' not found")

        portal = app_config.payment_portal_url.rstrip("/")
        if "/pay" in portal:
            pay_url = f"{portal}/{inv.qbo_invoice_id}"
        else:
            pay_url = f"{portal}/pay/{inv.qbo_invoice_id}"

        qr_bytes = generate_payment_qr(pay_url, box_size=6, border=2)
        return Response(content=qr_bytes, media_type="image/png")

    @app.post("/api/invoices/{identifier}/send-email", tags=["Invoices"])
    def send_invoice_email_endpoint(identifier: str, req: Optional[SendEmailRequest] = None):
        """Dispatch invoice email with attached vector PDF via SMTP or sandbox mock."""
        inv = (
            ledger.get_invoice_by_id(identifier)
            or ledger.get_invoice_by_doc_number(identifier)
            or ledger.get_invoice_by_order_id(identifier)
        )
        if not inv:
            raise HTTPException(status_code=404, detail=f"Invoice '{identifier}' not found")

        r = req or SendEmailRequest()
        try:
            dispatch = mailer.send_invoice_email(
                invoice=inv,
                recipient_email=r.recipient_email,
                subject=r.subject,
                text_body=r.text_body,
                html_body=r.html_body,
            )
            return {
                "status": "SUCCESS",
                "dispatch": dispatch.model_dump(mode="json"),
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to dispatch invoice email: {exc}")

    @app.get("/api/invoices/{identifier}/dispatches", response_model=List[EmailDispatchRecord], tags=["Invoices"])
    def get_invoice_email_dispatches(identifier: str):
        """Retrieve audit history of emails dispatched for this invoice."""
        inv = (
            ledger.get_invoice_by_id(identifier)
            or ledger.get_invoice_by_doc_number(identifier)
            or ledger.get_invoice_by_order_id(identifier)
        )
        if not inv:
            raise HTTPException(status_code=404, detail=f"Invoice '{identifier}' not found")
        return ledger.get_email_dispatches(invoice_id=inv.qbo_invoice_id)

    # ========================================================================
    # Hosted Customer Payment Portal Pages
    # ========================================================================

    @app.get("/pay/{identifier}", response_class=HTMLResponse, tags=["Stripe Checkout"])
    def customer_payment_portal(identifier: str):
        """Customer-facing self-service invoice payment portal."""
        inv = (
            ledger.get_invoice_by_id(identifier)
            or ledger.get_invoice_by_doc_number(identifier)
            or ledger.get_invoice_by_order_id(identifier)
        )
        if not inv:
            return HTMLResponse(
                status_code=404,
                content=f"""<!DOCTYPE html>
<html>
<head><title>Invoice Not Found</title><script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-slate-50 flex items-center justify-center min-h-screen p-4 font-sans text-slate-800">
  <div class="bg-white p-8 rounded-xl shadow-md max-w-md w-full text-center border border-slate-200">
    <div class="w-12 h-12 bg-rose-100 text-rose-600 rounded-full flex items-center justify-center mx-auto mb-4 font-bold text-xl">!</div>
    <h1 class="text-xl font-bold mb-2">Invoice Not Found</h1>
    <p class="text-sm text-slate-500 mb-6">Could not locate invoice reference: <code class="font-mono text-slate-700">{identifier}</code></p>
    <a href="/" class="text-sm text-indigo-600 hover:underline">Return to Dashboard</a>
  </div>
</body>
</html>""",
            )

        is_paid = inv.balance_due <= Decimal("0.00") or inv.payment_status == PaymentStatus.PAID
        badge_cls = "bg-emerald-100 text-emerald-800 border-emerald-300" if is_paid else "bg-amber-100 text-amber-800 border-amber-300"
        status_text = "PAID IN FULL" if is_paid else inv.payment_status.value

        checkout_card = ""
        if is_paid:
            checkout_card = f"""
            <div class="p-6 bg-emerald-50 rounded-xl border border-emerald-200 text-center">
                <div class="w-12 h-12 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center mx-auto mb-3">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                </div>
                <h3 class="text-lg font-bold text-emerald-900">Invoice Fully Settled</h3>
                <p class="text-sm text-emerald-700 mt-1">Thank you! No further balance is outstanding for this invoice.</p>
                <div class="mt-5 flex justify-center gap-3">
                    <a href="/api/invoices/{inv.doc_number}/html" target="_blank" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-semibold shadow transition">View Invoice Receipt</a>
                    <a href="/" class="px-4 py-2 bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 rounded-lg text-sm font-semibold transition">Back to Dashboard</a>
                </div>
            </div>
            """
        else:
            checkout_card = f"""
            <div class="space-y-6">
                <div class="border border-slate-200 rounded-xl p-5 bg-slate-50">
                    <h3 class="text-sm font-bold text-slate-800 uppercase tracking-wider mb-3">Select Payment Method</h3>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <label class="flex items-center p-3.5 bg-white border border-indigo-200 rounded-lg shadow-xs cursor-pointer hover:border-indigo-500 transition">
                            <input type="radio" name="payment_channel" value="card" checked class="text-indigo-600 focus:ring-indigo-500 h-4 w-4">
                            <div class="ml-3">
                                <span class="block text-sm font-semibold text-slate-900">Credit or Debit Card</span>
                                <span class="block text-xs text-slate-500">Visa, Mastercard, Amex, Apple Pay, Google Pay</span>
                            </div>
                        </label>
                        <label class="flex items-center p-3.5 bg-white border border-slate-200 rounded-lg shadow-xs cursor-pointer hover:border-indigo-500 transition">
                            <input type="radio" name="payment_channel" value="ach" class="text-indigo-600 focus:ring-indigo-500 h-4 w-4">
                            <div class="ml-3">
                                <span class="block text-sm font-semibold text-slate-900">US Bank Account (ACH)</span>
                                <span class="block text-xs text-slate-500">Direct debit transfer (0.8% capped fee)</span>
                            </div>
                        </label>
                    </div>
                </div>

                <div class="flex flex-col sm:flex-row gap-3">
                    <button onclick="startCheckout()" id="checkoutBtn" class="flex-1 py-3 px-4 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-bold shadow-md transition flex items-center justify-center gap-2 cursor-pointer">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z"></path></svg>
                        Proceed to Stripe Checkout (${inv.balance_due:.2f})
                    </button>
                    <button onclick="instantSettle()" id="instantBtn" class="py-3 px-4 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-sm font-bold shadow-md transition flex items-center justify-center gap-2 cursor-pointer">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
                        1-Click Test Settle
                    </button>
                </div>

                <div class="text-center text-xs text-slate-400 flex items-center justify-center gap-1.5">
                    <svg class="w-3.5 h-3.5 text-slate-400" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z" clip-rule="evenodd"></path></svg>
                    <span>256-Bit SSL Encrypted &amp; Reconciled with QuickBooks Online</span>
                </div>
            </div>
            """

        portal_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Customer Payment Portal — Invoice {inv.doc_number}</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-50 font-sans text-slate-800 min-h-screen">
    <!-- Navigation Bar -->
    <header class="bg-white border-b border-slate-200">
        <div class="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
            <div class="flex items-center space-x-3">
                <div class="w-9 h-9 bg-indigo-600 text-white rounded-lg flex items-center justify-center font-bold text-lg">Q</div>
                <div>
                    <h1 class="text-base font-bold text-slate-900">{app_config.company_name}</h1>
                    <p class="text-xs text-slate-500">Customer Payment &amp; Accounting Portal</p>
                </div>
            </div>
            <div class="flex items-center space-x-2">
                <a href="/api/invoices/{inv.doc_number}/html" target="_blank" class="text-xs font-semibold text-slate-600 hover:text-indigo-600 bg-slate-100 hover:bg-slate-200 px-3 py-1.5 rounded-lg transition">View Invoice HTML</a>
                <a href="/" class="text-xs font-semibold text-indigo-600 hover:underline px-2">Dashboard</a>
            </div>
        </div>
    </header>

    <main class="max-w-4xl mx-auto px-4 py-8">
        <div class="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
            <!-- Header Summary Banner -->
            <div class="p-6 md:p-8 bg-gradient-to-r from-slate-900 to-indigo-950 text-white flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <div class="flex items-center gap-2 mb-1">
                        <span class="text-xs uppercase tracking-wider font-semibold text-indigo-300">Invoice Statement</span>
                        <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold border {badge_cls}">{status_text}</span>
                    </div>
                    <h2 class="text-2xl font-black">{inv.doc_number}</h2>
                    <p class="text-xs text-slate-300 mt-1">Billed to: <span class="font-semibold text-white">{inv.customer_name}</span> ({inv.customer_email})</p>
                </div>
                <div class="text-left md:text-right">
                    <div class="text-xs text-slate-300 uppercase tracking-wider">Balance Due</div>
                    <div class="text-3xl font-black text-indigo-400 mt-0.5">${inv.balance_due:.2f} <span class="text-xs font-normal text-slate-300">{inv.currency}</span></div>
                    <div class="text-xs text-slate-400 mt-1">Due Date: {inv.due_date or 'Due Upon Receipt'}</div>
                </div>
            </div>

            <!-- Invoice Details Grid -->
            <div class="p-6 md:p-8">
                <div class="grid grid-cols-2 md:grid-cols-4 gap-4 pb-6 border-b border-slate-100 text-sm">
                    <div>
                        <div class="text-xs text-slate-400">Transaction Date</div>
                        <div class="font-semibold text-slate-700 mt-0.5">{inv.txn_date}</div>
                    </div>
                    <div>
                        <div class="text-xs text-slate-400">Order Reference</div>
                        <div class="font-mono text-slate-700 mt-0.5">{inv.order_id or 'N/A'}</div>
                    </div>
                    <div>
                        <div class="text-xs text-slate-400">QuickBooks ID</div>
                        <div class="font-mono text-slate-700 mt-0.5">{inv.qbo_invoice_id}</div>
                    </div>
                    <div>
                        <div class="text-xs text-slate-400">Total Invoiced</div>
                        <div class="font-semibold text-slate-900 mt-0.5">${inv.total_amount:.2f}</div>
                    </div>
                </div>

                <!-- PDF Export & Mobile Payment QR Code -->
                <div class="flex flex-col sm:flex-row items-center justify-between gap-4 p-4 bg-slate-50 border border-slate-200 rounded-xl mt-6">
                    <div class="flex items-center gap-3">
                        <img src="/api/invoices/{inv.qbo_invoice_id}/qr" alt="Payment QR Code" class="w-16 h-16 rounded border border-slate-300 bg-white p-1 shadow-xs" />
                        <div>
                            <div class="text-xs font-bold text-slate-800">Scan QR Code to Pay on Mobile</div>
                            <div class="text-xs text-slate-500">Scan with your smartphone camera to open instant checkout.</div>
                        </div>
                    </div>
                    <div class="flex items-center gap-2 w-full sm:w-auto">
                        <a href="/api/invoices/{inv.qbo_invoice_id}/pdf" target="_blank" class="flex-1 sm:flex-none inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold bg-rose-600 hover:bg-rose-700 text-white shadow-xs transition">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                            Download PDF
                        </a>
                        <button onclick="dispatchPortalEmail()" id="emailBtn" class="flex-1 sm:flex-none inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white shadow-xs transition">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path></svg>
                            Email PDF
                        </button>
                    </div>
                </div>

                <!-- Payment Action Card -->
                <div class="mt-6">
                    {checkout_card}
                </div>
            </div>
        </div>
    </main>

    <script>
        async function dispatchPortalEmail() {{
            const btn = document.getElementById('emailBtn');
            btn.disabled = true;
            btn.innerText = 'Sending...';
            try {{
                const res = await fetch('/api/invoices/{inv.qbo_invoice_id}/send-email', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{}})
                }});
                const data = await res.json();
                if (data.status === 'SUCCESS') {{
                    alert('Invoice PDF successfully sent to ' + data.dispatch.recipient_email + ' (' + data.dispatch.status + ')');
                }} else {{
                    alert('Failed: ' + JSON.stringify(data));
                }}
            }} catch (e) {{
                alert('Error: ' + e);
            }} finally {{
                btn.disabled = false;
                btn.innerText = 'Email PDF';
            }}
        }}

        async function startCheckout() {{
            const btn = document.getElementById('checkoutBtn');
            btn.disabled = true;
            btn.innerText = 'Creating Checkout Session...';
            try {{
                const res = await fetch('/api/invoices/{inv.qbo_invoice_id}/checkout-session', {{method: 'POST'}});
                if (!res.ok) throw new Error(await res.text());
                const session = await res.json();
                window.location.href = session.checkout_url;
            }} catch (err) {{
                alert('Error launching Stripe Checkout: ' + err);
                btn.disabled = false;
                btn.innerText = 'Proceed to Stripe Checkout (${inv.balance_due:.2f})';
            }}
        }}

        async function instantSettle() {{
            const btn = document.getElementById('instantBtn');
            btn.disabled = true;
            btn.innerText = 'Settling Payment...';
            try {{
                const channel = document.querySelector('input[name="payment_channel"]:checked')?.value || 'card';
                const method = channel === 'ach' ? 'ACH' : 'CreditCard';
                const res = await fetch('/api/pay/simulate', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{invoice_id: '{inv.qbo_invoice_id}', payment_method: method}})
                }});
                const data = await res.json();
                if (data.success) {{
                    window.location.href = '/pay/success/{inv.qbo_invoice_id}?amount=' + data.amount_paid;
                }} else {{
                    alert('Settlement failed: ' + data.message);
                    btn.disabled = false;
                    btn.innerText = '1-Click Test Settle';
                }}
            }} catch (err) {{
                alert('Error: ' + err);
                btn.disabled = false;
                btn.innerText = '1-Click Test Settle';
            }}
        }}
    </script>
</body>
</html>"""
        return HTMLResponse(content=portal_html)

    @app.get("/pay/checkout/{session_id}", response_class=HTMLResponse, tags=["Stripe Checkout"])
    def mock_stripe_checkout_page(session_id: str):
        """Hosted Stripe Checkout simulation page for sandbox test environments."""
        session = stripe_engine.get_checkout_session(session_id)
        if not session:
            return HTMLResponse(status_code=404, content="<h1>Stripe Checkout Session Expired or Not Found</h1>")

        checkout_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stripe Checkout Sandbox — {session.doc_number}</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-100 min-h-screen flex items-center justify-center p-4 font-sans">
    <div class="bg-white rounded-2xl shadow-xl max-w-2xl w-full overflow-hidden border border-slate-200 grid grid-cols-1 md:grid-cols-2">
        <!-- Left: Summary -->
        <div class="bg-slate-900 text-white p-6 md:p-8 flex flex-col justify-between">
            <div>
                <div class="inline-flex items-center px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 text-xs font-semibold mb-4">
                    STRIPE TESTMODE SANDBOX
                </div>
                <div class="text-xs text-slate-400">Pay {app_config.company_name}</div>
                <div class="text-3xl font-black text-white mt-1">${session.amount_total:.2f}</div>
                <div class="text-xs text-slate-400 mt-4 border-t border-slate-800 pt-4">
                    <div>Invoice: <strong class="text-slate-200 font-mono">{session.doc_number}</strong></div>
                    <div class="mt-1">Customer: <strong class="text-slate-200">{session.customer_name or 'N/A'}</strong></div>
                    <div class="mt-1">Email: <span class="text-slate-300 font-mono text-xs">{session.customer_email or 'N/A'}</span></div>
                </div>
            </div>
            <div class="mt-8 text-xs text-slate-500">
                Simulated Stripe Checkout Session: <span class="font-mono text-slate-400">{session.session_id}</span>
            </div>
        </div>

        <!-- Right: Form -->
        <div class="p-6 md:p-8 flex flex-col justify-between">
            <div>
                <h3 class="text-base font-bold text-slate-900 mb-4">Payment Information</h3>
                <div class="space-y-4">
                    <div>
                        <label class="block text-xs font-semibold text-slate-600 mb-1">Card Number</label>
                        <input type="text" value="4242 &bull;&bull;&bull;&bull; &bull;&bull;&bull;&bull; 4242" readonly class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm font-mono text-slate-700">
                    </div>
                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-xs font-semibold text-slate-600 mb-1">Expiration</label>
                            <input type="text" value="12 / 28" readonly class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm font-mono text-slate-700">
                        </div>
                        <div>
                            <label class="block text-xs font-semibold text-slate-600 mb-1">CVC</label>
                            <input type="text" value="888" readonly class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm font-mono text-slate-700">
                        </div>
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-slate-600 mb-1">Name on Card</label>
                        <input type="text" value="{session.customer_name or 'Authorized Signer'}" readonly class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-700">
                    </div>
                </div>
            </div>

            <div class="mt-6">
                <button onclick="submitPayment()" id="payBtn" class="w-full py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-bold text-sm shadow transition flex items-center justify-center gap-2 cursor-pointer">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                    Authorize Payment (${session.amount_total:.2f})
                </button>
                <div class="text-center mt-3">
                    <a href="{session.cancel_url}" class="text-xs text-slate-500 hover:underline">Cancel and return</a>
                </div>
            </div>
        </div>
    </div>

    <script>
        async function submitPayment() {{
            const btn = document.getElementById('payBtn');
            btn.disabled = true;
            btn.innerText = 'Processing Authorization...';
            try {{
                const res = await fetch('/api/pay/simulate', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{invoice_id: '{session.qbo_invoice_id}', amount: {float(session.amount_total)}}})
                }});
                const data = await res.json();
                if (data.success) {{
                    window.location.href = '{session.success_url}';
                }} else {{
                    alert('Error: ' + data.message);
                    btn.disabled = false;
                    btn.innerText = 'Authorize Payment';
                }}
            }} catch (err) {{
                alert('Authorization failed: ' + err);
                btn.disabled = false;
                btn.innerText = 'Authorize Payment';
            }}
        }}
    </script>
</body>
</html>"""
        return HTMLResponse(content=checkout_html)

    @app.get("/pay/success/{identifier}", response_class=HTMLResponse, tags=["Stripe Checkout"])
    def payment_success_page(identifier: str, amount: Optional[float] = Query(None)):
        """Customer payment confirmation and receipt acknowledgment page."""
        inv = (
            ledger.get_invoice_by_id(identifier)
            or ledger.get_invoice_by_doc_number(identifier)
            or ledger.get_invoice_by_order_id(identifier)
        )
        doc_num = inv.doc_number if inv else identifier
        cust_name = inv.customer_name if inv else "Valued Customer"
        paid_amt = f"${amount:.2f}" if amount else (f"${inv.total_amount:.2f}" if inv else "$0.00")
        bal_due = f"${inv.balance_due:.2f}" if inv else "$0.00"

        success_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Payment Successful — Invoice {doc_num}</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-50 min-h-screen flex items-center justify-center p-4 font-sans text-slate-800">
    <div class="bg-white rounded-2xl shadow-md border border-slate-200 max-w-md w-full p-8 text-center">
        <div class="w-16 h-16 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"></path></svg>
        </div>
        <h1 class="text-2xl font-black text-slate-900 mb-1">Payment Successful!</h1>
        <p class="text-xs text-slate-500 mb-6">Your transaction has been processed and automatically reconciled with QuickBooks Online.</p>

        <div class="bg-slate-50 rounded-xl p-4 border border-slate-100 text-left text-sm space-y-2.5 mb-6">
            <div class="flex justify-between"><span class="text-slate-500">Invoice:</span> <strong class="font-mono text-slate-800">{doc_num}</strong></div>
            <div class="flex justify-between"><span class="text-slate-500">Customer:</span> <span class="font-semibold text-slate-800">{cust_name}</span></div>
            <div class="flex justify-between"><span class="text-slate-500">Amount Paid:</span> <span class="font-bold text-emerald-600">{paid_amt}</span></div>
            <div class="flex justify-between"><span class="text-slate-500">Remaining Balance:</span> <span class="font-mono text-slate-800">{bal_due}</span></div>
            <div class="flex justify-between"><span class="text-slate-500">QBO Status:</span> <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-emerald-100 text-emerald-800">RECONCILED</span></div>
        </div>

        <div class="space-y-2">
            <a href="/api/invoices/{doc_num}/html" target="_blank" class="block w-full py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-semibold shadow transition">View Invoice Receipt</a>
            <a href="/pay/{identifier}" class="block w-full py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-sm font-semibold transition">Back to Portal</a>
            <a href="/" class="block text-xs text-slate-400 hover:underline pt-2">Return to Dashboard</a>
        </div>
    </div>
</body>
</html>"""
        return HTMLResponse(content=success_html)

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
                <td class="py-3 px-4 text-center space-x-1">
                    <a href="/pay/{inv.qbo_invoice_id}" target="_blank" class="inline-flex items-center px-2 py-1 rounded text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white transition shadow-xs">Pay Portal</a>
                    <a href="/api/invoices/{inv.qbo_invoice_id}/pdf" target="_blank" class="inline-flex items-center px-2 py-1 rounded text-xs font-semibold bg-rose-600 hover:bg-rose-700 text-white transition shadow-xs">PDF</a>
                    <button onclick="sendInvoiceEmail('{inv.qbo_invoice_id}')" class="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-emerald-600 hover:bg-emerald-700 text-white transition shadow-xs">Email</button>
                    <a href="/api/invoices/{inv.doc_number}/html" target="_blank" class="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-700 transition">HTML</a>
                </td>
            </tr>
            """

        if not invoices:
            rows_html = """<tr><td colspan="9" class="text-center py-12 text-slate-400">No invoices generated yet. Use the CLI or API to create one!</td></tr>"""

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
                            <th class="py-3 px-4 text-center">Actions</th>
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

        async function sendInvoiceEmail(invoiceId) {{
            if (!confirm('Dispatch invoice email with attached vector PDF?')) return;
            try {{
                const res = await fetch('/api/invoices/' + invoiceId + '/send-email', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{}})
                }});
                const data = await res.json();
                if (data.status === 'SUCCESS') {{
                    alert('Invoice PDF sent to ' + data.dispatch.recipient_email + ' (' + data.dispatch.status + ')');
                }} else {{
                    alert('Error: ' + JSON.stringify(data));
                }}
            }} catch (err) {{
                alert('Failed to send invoice email: ' + err);
            }}
        }}
    </script>
</body>
</html>"""
        return dashboard_html

    return app


# Default app instance
app = create_app()

