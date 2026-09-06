"""
Command Line Interface for QuickBooks Online Invoicing.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional
from uuid import uuid4

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from qb_invoicing import __version__
from qb_invoicing.config import Settings
from qb_invoicing.ledger import LedgerRepository
from qb_invoicing.mailer import InvoiceMailer
from qb_invoicing.models import (
    InvoiceRecord,
    OrderData,
    PaymentRecord,
    PaymentStatus,
)
from qb_invoicing.payment_tracker import PaymentStatusTracker
from qb_invoicing.pdf_generator import InvoicePDFGenerator
from qb_invoicing.qbo_client import QuickBooksClient
from qb_invoicing.renderer import InvoiceRenderer
from qb_invoicing.transformer import OrderTransformer

console = Console()


def get_components():
    """Helper to initialize client, ledger, transformer, and payment tracker."""
    cfg = Settings.load()
    client = QuickBooksClient(cfg)
    ledger = LedgerRepository(cfg.database_path)
    tracker = PaymentStatusTracker(client, ledger)
    transformer = OrderTransformer(default_terms_days=cfg.default_payment_terms_days)
    return client, ledger, tracker, transformer, cfg


@click.group(context_settings=dict(help_option_names=["-h", "--help"]))
@click.version_option(version=__version__, prog_name="qb-invoicing", message="%(prog)s v%(version)s")
def cli():
    """QuickBooks Online Invoice Generator & Payment Status Tracker."""
    pass


@cli.command("init-db")
def init_db_cmd():
    """Initialize or verify the local SQLite database ledger."""
    _, ledger, _, _, cfg = get_components()
    ledger.init_db()
    console.print(f"[bold green][OK][/bold green] Database initialized at: [cyan]{cfg.database_path}[/cyan]")


@cli.command("generate")
@click.option("--order", "-o", "order_path", required=True, type=click.Path(exists=True), help="Path to order JSON file")
@click.option("--customer-id", "-c", default=None, help="QuickBooks Customer ID (optional override)")
@click.option("--doc-number", "-d", default=None, help="Custom Invoice DocNumber (optional)")
@click.option("--export-html", is_flag=True, help="Export rendered HTML invoice to exports dir")
def generate_cmd(order_path: str, customer_id: Optional[str], doc_number: Optional[str], export_html: bool):
    """Generate a QuickBooks Online invoice from an order data JSON file."""
    client, ledger, _, transformer, cfg = get_components()

    with console.status("[bold green]Loading and validating order data..."):
        order = transformer.load_order_from_file(order_path)
        ledger.save_order(order)

    # Ensure customer exists or resolve customer in QBO
    with console.status("[bold green]Syncing customer and generating QBO Invoice..."):
        qbo_customer = client.get_or_create_customer(
            name=order.customer.name,
            email=order.customer.email,
            company=order.customer.company_name,
        )
        resolved_cust_id = customer_id or str(qbo_customer.get("Id", "1"))

        # Transform to QBO payload
        qbo_payload = transformer.transform_to_qbo_invoice(
            order=order,
            qbo_customer_id=resolved_cust_id,
            doc_number=doc_number,
        )

        # Call QBO API (or Mock Engine)
        created_inv = client.create_invoice(qbo_payload)

    # Persist in local ledger
    qbo_id = str(created_inv.get("Id"))
    doc_num = str(created_inv.get("DocNumber", qbo_payload.DocNumber))
    total_amt = Decimal(str(created_inv.get("TotalAmt", order.computed_total)))
    bal_due = Decimal(str(created_inv.get("Balance", total_amt)))

    inv_record = InvoiceRecord(
        qbo_invoice_id=qbo_id,
        order_id=order.order_id,
        doc_number=doc_num,
        customer_name=order.customer.name,
        customer_email=order.customer.email,
        txn_date=qbo_payload.TxnDate,
        due_date=qbo_payload.DueDate,
        total_amount=total_amt,
        balance_due=bal_due,
        payment_status=PaymentStatus.PENDING if bal_due > 0 else PaymentStatus.PAID,
        currency=order.currency,
        raw_payload=qbo_payload.model_dump_json(),
        raw_response=json.dumps(created_inv),
    )
    ledger.save_invoice(inv_record)

    # Render results table
    table = Table(title=f"Invoice Generated: {doc_num}", show_header=True, header_style="bold magenta")
    table.add_column("Field", style="dim", width=20)
    table.add_column("Value", style="bold")

    table.add_row("QuickBooks ID", qbo_id)
    table.add_row("Doc / Invoice #", doc_num)
    table.add_row("Order ID", order.order_id)
    table.add_row("Customer", f"{order.customer.name} ({order.customer.email})")
    table.add_row("Txn Date", qbo_payload.TxnDate)
    table.add_row("Due Date", qbo_payload.DueDate or "Upon Receipt")
    table.add_row("Line Items Count", str(len(order.items)))
    table.add_row("Subtotal", f"${order.computed_subtotal:.2f} {order.currency}")
    if order.shipping_fee > 0:
        table.add_row("Shipping Fee", f"${order.shipping_fee:.2f} {order.currency}")
    if order.discount_total > 0:
        table.add_row("Discount Total", f"-${order.discount_total:.2f} {order.currency}")
    if order.computed_tax > 0:
        table.add_row("Tax Amount", f"${order.computed_tax:.2f} {order.currency}")
    table.add_row("Total Amount", f"[green]${total_amt:.2f} {order.currency}[/green]")
    table.add_row("Balance Due", f"[yellow]${bal_due:.2f} {order.currency}[/yellow]")
    table.add_row("Initial Status", f"[bold yellow]{inv_record.payment_status.value}[/bold yellow]")

    console.print(table)

    if export_html:
        export_dir = Path(cfg.exports_dir)
        export_dir.mkdir(parents=True, exist_ok=True)
        html_path = export_dir / f"{doc_num}.html"
        html_content = InvoiceRenderer.render_html(inv_record)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        console.print(f"[bold green][OK][/bold green] Exported HTML invoice to: [cyan]{html_path}[/cyan]")


@cli.command("batch-generate")
@click.option("--file", "-f", "batch_file", required=True, type=click.Path(exists=True), help="Path to JSON file with array of orders")
def batch_generate_cmd(batch_file: str):
    """Batch generate invoices from a JSON file containing multiple orders."""
    client, ledger, _, transformer, _ = get_components()

    with open(batch_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        console.print("[bold red]Error:[/bold red] Batch file must contain a JSON array of orders.")
        raise click.Abort()

    console.print(f"[bold blue]Processing {len(data)} orders in batch...[/bold blue]")

    table = Table(title="Batch Invoicing Results", show_header=True)
    table.add_column("Order ID", style="cyan")
    table.add_column("Doc Number", style="bold")
    table.add_column("QBO ID", style="dim")
    table.add_column("Customer", style="magenta")
    table.add_column("Total", justify="right")
    table.add_column("Status", justify="center")

    success_count = 0
    for idx, item in enumerate(data, 1):
        try:
            order = transformer.parse_order(item)
            ledger.save_order(order)
            qbo_customer = client.get_or_create_customer(order.customer.name, order.customer.email)
            qbo_payload = transformer.transform_to_qbo_invoice(order, qbo_customer_id=str(qbo_customer.get("Id", "1")))
            created = client.create_invoice(qbo_payload)

            qbo_id = str(created.get("Id"))
            doc_num = str(created.get("DocNumber", qbo_payload.DocNumber))
            total_amt = Decimal(str(created.get("TotalAmt", order.computed_total)))
            bal = Decimal(str(created.get("Balance", total_amt)))

            record = InvoiceRecord(
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
            ledger.save_invoice(record)
            table.add_row(
                order.order_id,
                doc_num,
                qbo_id,
                order.customer.name,
                f"${total_amt:.2f}",
                f"[yellow]{record.payment_status.value}[/yellow]",
            )
            success_count += 1
        except Exception as e:
            table.add_row(
                item.get("order_id", f"Row {idx}"),
                "-",
                "-",
                item.get("customer", {}).get("name", "Unknown"),
                "-",
                f"[bold red]FAILED: {e}[/bold red]",
            )

    console.print(table)
    console.print(f"[bold green][OK][/bold green] Successfully generated {success_count}/{len(data)} invoices.")


@cli.command("status")
@click.argument("identifier")
def status_cmd(identifier: str):
    """Check live status of an invoice by QBO ID, DocNumber, or Order ID."""
    _, ledger, tracker, _, _ = get_components()

    # Try lookup by QBO ID, then DocNumber, then Order ID
    inv = (
        ledger.get_invoice_by_id(identifier)
        or ledger.get_invoice_by_doc_number(identifier)
        or ledger.get_invoice_by_order_id(identifier)
    )

    if not inv:
        console.print(f"[bold red]Error:[/bold red] No invoice found matching identifier: [yellow]{identifier}[/yellow]")
        return

    # Sync live state from QBO
    synced = tracker.sync_invoice_status(inv.qbo_invoice_id) or inv
    payments = ledger.get_payments_for_invoice(synced.qbo_invoice_id)

    status_color = {
        PaymentStatus.PAID: "green",
        PaymentStatus.PENDING: "yellow",
        PaymentStatus.PARTIAL: "blue",
        PaymentStatus.OVERDUE: "red",
        PaymentStatus.DRAFT: "white",
        PaymentStatus.VOIDED: "dim",
    }.get(synced.payment_status, "white")

    panel_text = (
        f"[bold]Invoice Number:[/bold] {synced.doc_number}\n"
        f"[bold]QuickBooks Online ID:[/bold] {synced.qbo_invoice_id}\n"
        f"[bold]Associated Order ID:[/bold] {synced.order_id}\n"
        f"[bold]Customer:[/bold] {synced.customer_name} <{synced.customer_email}>\n"
        f"[bold]Txn Date:[/bold] {synced.txn_date}  |  [bold]Due Date:[/bold] {synced.due_date or 'None'}\n\n"
        f"[bold]Total Invoiced:[/bold] ${synced.total_amount:.2f} {synced.currency}\n"
        f"[bold]Amount Paid:[/bold] ${(synced.total_amount - synced.balance_due):.2f} {synced.currency}\n"
        f"[bold]Balance Due:[/bold] ${synced.balance_due:.2f} {synced.currency}\n\n"
        f"[bold]Payment Status:[/bold] [{status_color}]{synced.payment_status.value}[/{status_color}]"
    )

    console.print(Panel(panel_text, title=f"QuickBooks Invoice Status", expand=False))

    if payments:
        p_table = Table(title="Payment History", show_header=True)
        p_table.add_column("Payment ID", style="dim")
        p_table.add_column("Txn Date")
        p_table.add_column("Method")
        p_table.add_column("Reference")
        p_table.add_column("Amount", justify="right", style="green")

        for p in payments:
            p_table.add_row(
                p.qbo_payment_id,
                p.txn_date,
                p.payment_method or "CreditCard",
                p.reference_num or "-",
                f"${p.amount:.2f}",
            )
        console.print(p_table)
    else:
        console.print("[dim italic]No payments recorded against this invoice yet.[/dim italic]")


@cli.command("record-payment")
@click.option("--invoice", "-i", "invoice_id", required=True, help="QBO Invoice ID or Doc Number")
@click.option("--amount", "-a", required=True, type=float, help="Payment amount")
@click.option("--method", "-m", default="CreditCard", help="Payment method (CreditCard, Check, BankTransfer)")
@click.option("--ref", "-r", default=None, help="Payment transaction reference number")
def record_payment_cmd(invoice_id: str, amount: float, method: str, ref: Optional[str]):
    """Record a payment in QuickBooks Online and update the invoice balance."""
    _, ledger, tracker, _, _ = get_components()

    inv = ledger.get_invoice_by_id(invoice_id) or ledger.get_invoice_by_doc_number(invoice_id)
    if not inv:
        console.print(f"[bold red]Error:[/bold red] Invoice '{invoice_id}' not found.")
        return

    pay_amt = Decimal(str(amount))
    try:
        payment = tracker.record_manual_payment(
            qbo_invoice_id=inv.qbo_invoice_id,
            amount=pay_amt,
            payment_method=method,
            reference_num=ref,
        )
        updated = ledger.get_invoice_by_id(inv.qbo_invoice_id)

        console.print(f"[bold green][OK][/bold green] Payment of [green]${pay_amt:.2f}[/green] recorded successfully!")
        console.print(f"  - Payment QBO ID: [cyan]{payment.qbo_payment_id}[/cyan]")
        console.print(f"  - New Invoice Balance: [yellow]${updated.balance_due:.2f}[/yellow]")
        console.print(f"  - Updated Status: [bold { 'green' if updated.payment_status == PaymentStatus.PAID else 'yellow' }]{updated.payment_status.value}[/]")
    except Exception as e:
        console.print(f"[bold red]Failed to record payment:[/bold red] {e}")


@cli.command("sync-payments")
def sync_payments_cmd():
    """Scan and reconcile all open invoices with QuickBooks Online."""
    _, _, tracker, _, _ = get_components()

    with console.status("[bold green]Reconciling open invoices with QuickBooks Online..."):
        checked, updated, summaries = tracker.sync_all_pending()

    console.print(f"[bold]Reconciliation Complete:[/bold] Checked {checked} open invoices, {updated} updated.")

    if summaries:
        table = Table(title="Updated Invoices", show_header=True)
        table.add_column("Doc #", style="cyan")
        table.add_column("Customer")
        table.add_column("Previous Status", style="dim")
        table.add_column("New Status", style="bold green")
        table.add_column("Previous Balance")
        table.add_column("New Balance", style="bold")

        for s in summaries:
            table.add_row(
                s["doc_number"],
                s["customer"],
                s["previous_status"],
                s["new_status"],
                f"${s['previous_balance']:.2f}",
                f"${s['new_balance']:.2f}",
            )
        console.print(table)


@cli.command("list-invoices")
@click.option("--status", "-s", type=click.Choice(["DRAFT", "PENDING", "PARTIAL", "PAID", "OVERDUE", "VOIDED"], case_sensitive=False), default=None)
@click.option("--limit", "-l", default=25, help="Max records to return")
def list_invoices_cmd(status: Optional[str], limit: int):
    """List tracked invoices from the local ledger."""
    _, ledger, _, _, _ = get_components()

    filter_status = PaymentStatus(status.upper()) if status else None
    invoices = ledger.list_invoices(status=filter_status, limit=limit)

    if not invoices:
        console.print("[dim]No invoices found in ledger.[/dim]")
        return

    table = Table(title=f"Invoices ({status or 'All'}) - Total {len(invoices)}", show_header=True)
    table.add_column("Doc Number", style="cyan bold")
    table.add_column("QBO ID", style="dim")
    table.add_column("Order ID", style="magenta")
    table.add_column("Customer")
    table.add_column("Txn Date")
    table.add_column("Due Date")
    table.add_column("Total", justify="right")
    table.add_column("Balance", justify="right")
    table.add_column("Status", justify="center")

    for inv in invoices:
        status_color = {
            PaymentStatus.PAID: "green",
            PaymentStatus.PENDING: "yellow",
            PaymentStatus.PARTIAL: "blue",
            PaymentStatus.OVERDUE: "red",
        }.get(inv.payment_status, "white")

        table.add_row(
            inv.doc_number,
            inv.qbo_invoice_id,
            inv.order_id,
            inv.customer_name,
            inv.txn_date,
            inv.due_date or "-",
            f"${inv.total_amount:.2f}",
            f"${inv.balance_due:.2f}",
            f"[{status_color}]{inv.payment_status.value}[/{status_color}]",
        )

    console.print(table)


@cli.command("metrics")
def metrics_cmd():
    """Display high-level financial summary and invoice status metrics."""
    _, ledger, _, _, _ = get_components()
    m = ledger.get_metrics()

    table = Table(title="Financial KPIs & Invoicing Metrics", show_header=True, header_style="bold blue")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Total Invoices Tracked", str(m.total_invoices))
    table.add_row("Total Invoiced Amount", f"[bold green]${m.total_invoiced_amount:.2f}[/bold green]")
    table.add_row("Total Amount Collected", f"[green]${m.total_collected_amount:.2f}[/green]")
    table.add_row("Total Outstanding Balance", f"[bold yellow]${m.total_outstanding_balance:.2f}[/bold yellow]")
    table.add_row("Paid Invoices", f"[green]{m.paid_invoices_count}[/green]")
    table.add_row("Partially Paid Invoices", f"[blue]{m.partial_invoices_count}[/blue]")
    table.add_row("Pending Invoices", f"[yellow]{m.pending_invoices_count}[/yellow]")
    table.add_row("Overdue Invoices", f"[bold red]{m.overdue_invoices_count}[/bold red]")

    console.print(table)


@cli.command("preview")
@click.option("--order", "-o", "order_path", required=True, type=click.Path(exists=True), help="Path to order JSON")
def preview_cmd(order_path: str):
    """Preview QuickBooks Online API payload and calculations without creating an invoice."""
    _, _, _, transformer, _ = get_components()
    order = transformer.load_order_from_file(order_path)
    qbo_payload = transformer.transform_to_qbo_invoice(order)

    console.print(Panel(
        f"[bold]Order ID:[/bold] {order.order_id}\n"
        f"[bold]Customer:[/bold] {order.customer.name} ({order.customer.email})\n"
        f"[bold]Subtotal:[/bold] ${order.computed_subtotal:.2f}\n"
        f"[bold]Tax ({order.tax_rate_percent}%):[/bold] ${order.computed_tax:.2f}\n"
        f"[bold]Shipping Fee:[/bold] ${order.shipping_fee:.2f}\n"
        f"[bold]Discount Total:[/bold] -${order.discount_total:.2f}\n"
        f"[bold green]Computed Total:[/bold green] ${order.computed_total:.2f} {order.currency}\n"
        f"[bold]Due Date:[/bold] {qbo_payload.DueDate}",
        title="Order Ingestion Preview",
    ))

    console.print("[bold]QuickBooks Online API v3 JSON Payload:[/bold]")
    console.print_json(qbo_payload.model_dump_json(exclude_none=True))


@cli.command("serve")
@click.option("--host", default="127.0.0.1", help="Host interface to bind")
@click.option("--port", default=8000, type=int, help="Port to listen on")
def serve_cmd(host: str, port: int):
    """Launch the FastAPI web dashboard and webhook server."""
    import uvicorn

    console.print(f"[bold green][OK][/bold green] Starting QuickBooks Invoicing Dashboard at: [cyan]http://{host}:{port}[/cyan]")
    console.print(f"  - QuickBooks Webhook: [cyan]http://{host}:{port}/api/webhooks/quickbooks[/cyan]")
    console.print(f"  - Stripe Webhook: [cyan]http://{host}:{port}/api/webhooks/stripe[/cyan]")
    console.print(f"  - Customer Payment Portal: [cyan]http://{host}:{port}/pay/:invoice_id[/cyan]")
    console.print(f"  - API Documentation: [cyan]http://{host}:{port}/docs[/cyan]")
    uvicorn.run("qb_invoicing.api:app", host=host, port=port, reload=False)


@cli.command("simulate-webhook")
@click.option("--entity", "-e", type=click.Choice(["Payment", "Invoice"]), default="Payment", help="Entity name")
@click.option("--operation", "-op", type=click.Choice(["Create", "Update", "Void"]), default="Create", help="Entity operation")
@click.option("--id", "-i", "entity_id", default="5001", help="QBO entity ID to trigger event for")
def simulate_webhook_cmd(entity: str, operation: str, entity_id: str):
    """Simulate an incoming Intuit webhook notification with valid HMAC-SHA256 signature."""
    from qb_invoicing.webhooks import WebhookProcessor, generate_qbo_webhook_signature

    client, ledger, tracker, _, cfg = get_components()
    processor = WebhookProcessor(client, ledger, tracker)

    payload = {
        "eventNotifications": [
            {
                "realmId": cfg.realm_id,
                "dataChangeEvent": {
                    "entities": [
                        {
                            "name": entity,
                            "id": entity_id,
                            "operation": operation,
                            "lastUpdated": datetime.now(timezone.utc).isoformat(),
                        }
                    ]
                },
            }
        ]
    }
    payload_bytes = json.dumps(payload).encode("utf-8")
    sig = generate_qbo_webhook_signature(payload_bytes, cfg.webhook_verifier_token)

    console.print("[bold blue]Simulating Intuit QuickBooks Online Webhook...[/bold blue]")
    console.print(f"  - Entity: [cyan]{entity}[/cyan] (ID: {entity_id})")
    console.print(f"  - Operation: [yellow]{operation}[/yellow]")
    console.print(f"  - Computed HMAC-SHA256: [dim]{sig}[/dim]")

    result = processor.process_payload(
        payload_bytes=payload_bytes,
        signature=sig,
        verifier_token=cfg.webhook_verifier_token,
    )

    console.print("[bold green][OK][/bold green] Webhook processed successfully!")
    console.print_json(json.dumps(result))


@cli.command("aging-report")
@click.option("--as-of", "as_of_date", default=None, help="Reference evaluation date (YYYY-MM-DD)")
def aging_report_cmd(as_of_date: Optional[str]):
    """Display Accounts Receivable aging schedule report with aging buckets."""
    from qb_invoicing.dunning import DunningEngine

    _, ledger, _, _, cfg = get_components()
    engine = DunningEngine(ledger=ledger, settings=cfg)
    report = engine.get_aging_schedule(as_of_date=as_of_date)

    # Summary table
    summary_table = Table(
        title=f"Accounts Receivable Aging Schedule (As of {report.as_of_date})",
        show_header=True,
        header_style="bold blue",
    )
    summary_table.add_column("Aging Bucket", style="bold")
    summary_table.add_column("Escalation Tier", style="cyan")
    summary_table.add_column("Amount", justify="right")

    summary_table.add_row("Current (Not Due)", "None", f"[green]${report.current_amount:.2f}[/green]")
    summary_table.add_row("1-30 Days Overdue", "Tier 1 (Friendly)", f"[blue]${report.days_1_30_amount:.2f}[/blue]")
    summary_table.add_row("31-60 Days Overdue", "Tier 2 (Urgent)", f"[yellow]${report.days_31_60_amount:.2f}[/yellow]")
    summary_table.add_row("61-90 Days Overdue", "Tier 3 (Final Demand)", f"[orange3]${report.days_61_90_amount:.2f}[/orange3]")
    summary_table.add_row("90+ Days Overdue", "Tier 4 (Collections)", f"[bold red]${report.days_over_90_amount:.2f}[/bold red]")
    summary_table.add_section()
    summary_table.add_row("Total Receivables", "All Tiers", f"[bold green]${report.total_receivables:.2f}[/bold green]")

    console.print(summary_table)

    # Detail table for open invoices
    if report.invoices:
        detail_table = Table(
            title=f"Receivables Ledger Breakdown ({len(report.invoices)} open invoices)",
            show_header=True,
            header_style="bold magenta",
        )
        detail_table.add_column("Doc #", style="bold")
        detail_table.add_column("Customer")
        detail_table.add_column("Due Date")
        detail_table.add_column("Overdue", justify="right")
        detail_table.add_column("Balance Due", justify="right")
        detail_table.add_column("Bucket", justify="center")

        bucket_color = {
            "Current": "green",
            "1-30 Days": "blue",
            "31-60 Days": "yellow",
            "61-90 Days": "orange3",
            "90+ Days": "red",
        }

        for inv in report.invoices:
            c = bucket_color.get(inv.bucket.value, "white")
            detail_table.add_row(
                inv.doc_number,
                inv.customer_name,
                inv.due_date,
                f"{inv.days_overdue} days",
                f"${inv.balance_due:.2f}",
                f"[{c}]{inv.bucket.value}[/{c}]",
            )
        console.print(detail_table)
    else:
        console.print("[dim]No open invoices currently tracked in ledger.[/dim]")


@cli.command("dunning-run")
@click.option("--as-of", "as_of_date", default=None, help="Reference evaluation date (YYYY-MM-DD)")
@click.option("--cooldown-days", default=7, type=int, help="Days to suppress consecutive reminder notices")
@click.option("--force", is_flag=True, help="Bypass cooldown check and evaluate all overdue invoices")
@click.option("--dry-run", is_flag=True, help="Simulate dunning cycle without recording sent notices")
def dunning_run_cmd(as_of_date: Optional[str], cooldown_days: int, force: bool, dry_run: bool):
    """Execute automated dunning cycle to evaluate and dispatch overdue escalation notices."""
    from qb_invoicing.dunning import DunningEngine

    _, ledger, _, _, cfg = get_components()
    engine = DunningEngine(ledger=ledger, settings=cfg)

    console.print("[bold blue]Executing Automated Dunning Escalation Cycle...[/bold blue]")
    if dry_run:
        console.print("[yellow][SIMULATION] Running in DRY-RUN mode. Notices will not be persisted as sent.[/yellow]")

    result = engine.run_dunning_cycle(
        as_of_date=as_of_date,
        cooldown_days=cooldown_days,
        force=force,
        dry_run=dry_run,
    )

    console.print(f"  - Invoices Evaluated: [bold]{result.evaluated_count}[/bold]")
    console.print(f"  - Current / Not Due: [green]{result.current_count}[/green]")
    console.print(f"  - Skipped (Cooldown): [yellow]{result.skipped_cooldown_count}[/yellow]")
    console.print(f"  - Notices Dispatched: [bold green]{result.notices_sent_count}[/bold green]")

    if result.notices:
        table = Table(
            title=f"Dunning Notices {'Simulated' if dry_run else 'Dispatched'}",
            show_header=True,
            header_style="bold green",
        )
        table.add_column("Doc #", style="bold")
        table.add_column("Customer")
        table.add_column("Tier", justify="center")
        table.add_column("Overdue", justify="right")
        table.add_column("Balance Due", justify="right")
        table.add_column("Subject")
        table.add_column("Status", justify="center")

        tier_color = {1: "blue", 2: "yellow", 3: "orange3", 4: "red"}

        for n in result.notices:
            tc = tier_color.get(n.escalation_level, "white")
            table.add_row(
                n.doc_number,
                n.customer_name,
                f"[{tc}]Tier {n.escalation_level}: {n.level_name}[/{tc}]",
                f"{n.days_overdue} days",
                f"${n.balance_due:.2f}",
                n.subject,
                f"[green]{n.status}[/green]",
            )
        console.print(table)
    else:
        console.print("[dim]No notices needed dispatching based on current due dates and cooldown rules.[/dim]")


@cli.command("dunning-history")
@click.option("--limit", default=25, type=int, help="Maximum number of historical notices to retrieve")
def dunning_history_cmd(limit: int):
    """View recent dunning escalation notice dispatch logs."""
    _, ledger, _, _, _ = get_components()
    history = ledger.get_dunning_history(limit=limit)

    if not history:
        console.print("[yellow]No dunning notices recorded in the ledger history.[/yellow]")
        return

    table = Table(
        title=f"Dunning Notice Audit Log (Last {len(history)})",
        show_header=True,
        header_style="bold blue",
    )
    table.add_column("Doc #", style="bold")
    table.add_column("Customer")
    table.add_column("Escalation Tier")
    table.add_column("Overdue", justify="right")
    table.add_column("Balance", justify="right")
    table.add_column("Dispatched At")
    table.add_column("Status", justify="center")

    tier_color = {1: "blue", 2: "yellow", 3: "orange3", 4: "red"}

    for h in history:
        tc = tier_color.get(h.escalation_level, "white")
        table.add_row(
            h.doc_number,
            h.customer_name,
            f"[{tc}]Tier {h.escalation_level}: {h.level_name}[/{tc}]",
            f"{h.days_overdue} days",
            f"${h.balance_due:.2f}",
            h.sent_at.strftime("%Y-%m-%d %H:%M"),
            f"[green]{h.status}[/green]",
        )

    console.print(table)


@cli.command("checkout")
@click.option("--invoice", "-i", "identifier", required=True, help="Invoice ID or DocNumber to generate checkout session for")
def checkout_cmd(identifier: str):
    """Generate a self-service Stripe Checkout session and payment portal link."""
    from qb_invoicing.stripe_engine import StripeCheckoutEngine

    _, ledger, _, _, cfg = get_components()
    engine = StripeCheckoutEngine(
        api_key=cfg.stripe_api_key,
        webhook_secret=cfg.stripe_webhook_secret,
        use_mock=cfg.stripe_use_mock,
    )

    inv = (
        ledger.get_invoice_by_id(identifier)
        or ledger.get_invoice_by_doc_number(identifier)
        or ledger.get_invoice_by_order_id(identifier)
    )
    if not inv:
        console.print(f"[bold red][ERROR][/bold red] Invoice '{identifier}' not found in ledger database.")
        return

    session = engine.create_checkout_session(inv)

    console.print(f"[bold green][OK][/bold green] Created Stripe Checkout Session for Invoice [bold cyan]{inv.doc_number}[/bold cyan]:")
    table = Table(show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("Session ID", f"[yellow]{session.session_id}[/yellow]")
    table.add_row("Doc #", session.doc_number)
    table.add_row("Customer", session.customer_name or "N/A")
    table.add_row("Amount", f"${session.amount_total:.2f} {session.currency.upper()}")
    table.add_row("Payment Status", session.payment_status)
    table.add_row("Checkout URL", f"[cyan]{session.checkout_url}[/cyan]")
    table.add_row("Customer Portal", f"[cyan]{cfg.payment_portal_url.rstrip('/')}/pay/{inv.qbo_invoice_id}[/cyan]")
    console.print(table)


@cli.command("simulate-stripe-payment")
@click.option("--invoice", "-i", "identifier", required=True, help="Invoice ID or DocNumber to settle")
@click.option("--amount", "-a", type=float, default=None, help="Amount to pay (defaults to remaining balance)")
@click.option("--method", "-m", type=click.Choice(["card", "ach"], case_sensitive=False), default="card", help="Payment method")
def simulate_stripe_payment_cmd(identifier: str, amount: Optional[float], method: str):
    """Simulate an incoming Stripe payment webhook with valid HMAC-SHA256 signature and auto-reconciliation."""
    from qb_invoicing.stripe_engine import StripeCheckoutEngine

    client, ledger, tracker, _, cfg = get_components()
    engine = StripeCheckoutEngine(
        api_key=cfg.stripe_api_key,
        webhook_secret=cfg.stripe_webhook_secret,
        use_mock=cfg.stripe_use_mock,
    )

    inv = (
        ledger.get_invoice_by_id(identifier)
        or ledger.get_invoice_by_doc_number(identifier)
        or ledger.get_invoice_by_order_id(identifier)
    )
    if not inv:
        console.print(f"[bold red][ERROR][/bold red] Invoice '{identifier}' not found in ledger database.")
        return

    pay_amount = Decimal(str(amount)) if amount is not None else inv.balance_due
    if pay_amount <= Decimal("0.00"):
        pay_amount = inv.total_amount

    cents = int(pay_amount * 100)
    pm_type = "us_bank_account" if method.lower() == "ach" else "card"
    now_ts = int(time.time())

    mock_event = {
        "id": f"evt_cli_{uuid4().hex[:12]}",
        "object": "event",
        "type": "checkout.session.completed",
        "created": now_ts,
        "data": {
            "object": {
                "id": f"cs_cli_{uuid4().hex[:16]}",
                "payment_intent": f"pi_cli_{uuid4().hex[:16]}",
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

    payload_bytes = json.dumps(mock_event).encode("utf-8")
    sig_header = engine.generate_signed_webhook_header(payload_bytes, timestamp=now_ts)

    console.print(f"[bold blue]Simulating Stripe Webhook ([yellow]{method.upper()}[/yellow])...[/bold blue]")
    console.print(f"  - Invoice: [cyan]{inv.doc_number}[/cyan] (QBO ID: {inv.qbo_invoice_id})")
    console.print(f"  - Amount: [bold green]${pay_amount:.2f}[/bold green]")
    console.print(f"  - Computed Stripe-Signature HMAC-SHA256: [dim]{sig_header[:40]}...[/dim]")

    # Verify signature
    valid = engine.verify_webhook_signature(payload_bytes, sig_header)
    if not valid:
        console.print("[bold red][FAILED][/bold red] Stripe signature verification failed!")
        return

    result = engine.process_webhook_event(
        event_dict=mock_event,
        ledger=ledger,
        payment_tracker=tracker,
        qbo_client=client,
    )

    if result.success:
        console.print("[bold green][OK][/bold green] Stripe Payment Auto-Settled Successfully!")
        table = Table(show_header=False)
        table.add_column("Field", style="bold")
        table.add_column("Value")
        table.add_row("Invoice Doc #", result.doc_number)
        table.add_row("Amount Paid", f"${result.amount_paid:.2f}")
        table.add_row("Remaining Balance", f"${result.new_balance:.2f}")
        table.add_row("New Payment Status", f"[bold green]{result.payment_status.value}[/bold green]")
        table.add_row("QBO Payment ID", str(result.qbo_payment_id))
        table.add_row("Message", result.message)
        console.print(table)
    else:
        console.print(f"[bold red][ERROR][/bold red] Settlement failed: {result.message}")


@cli.command("export-pdf")
@click.option("--invoice", "-i", "identifier", required=True, help="Invoice DocNumber, QBO ID, or Order ID")
@click.option("--output", "-o", "output_path", default=None, help="Custom target PDF destination path")
@click.option("--portal-url", default=None, help="Payment portal base URL for the QR code")
def export_pdf_cmd(identifier: str, output_path: Optional[str], portal_url: Optional[str]):
    """Export an audit-compliant vector PDF invoice with embedded payment QR code."""
    _, ledger, _, _, cfg = get_components()
    inv = (
        ledger.get_invoice_by_id(identifier)
        or ledger.get_invoice_by_doc_number(identifier)
        or ledger.get_invoice_by_order_id(identifier)
    )
    if not inv:
        console.print(f"[bold red][ERROR][/bold red] Invoice '{identifier}' not found in local ledger.")
        return

    order = ledger.get_order(inv.order_id) if inv.order_id else None
    generator = InvoicePDFGenerator(cfg)

    resolved_url = None
    if portal_url:
        p = portal_url.rstrip("/")
        resolved_url = f"{p}/{inv.qbo_invoice_id}" if "/pay" in p else f"{p}/pay/{inv.qbo_invoice_id}"

    with console.status(f"[bold green]Generating vector PDF for Invoice {inv.doc_number}..."):
        saved_path = generator.save_pdf(
            invoice=inv,
            output_path=output_path,
            payment_url=resolved_url,
            order=order,
        )

    console.print(f"[bold green][OK][/bold green] Vector PDF exported to: [cyan]{saved_path}[/cyan]")
    table = Table(title=f"Invoice PDF Export: {inv.doc_number}", show_header=False)
    table.add_column("Property", style="bold")
    table.add_column("Detail")
    table.add_row("Document #", inv.doc_number)
    table.add_row("Customer", f"{inv.customer_name} ({inv.customer_email})")
    table.add_row("Total Amount", f"${inv.total_amount:.2f} {inv.currency}")
    table.add_row("Balance Due", f"${inv.balance_due:.2f} {inv.currency}")
    table.add_row("Status", f"[{inv.payment_status.value}]")
    table.add_row("File Size", f"{saved_path.stat().st_size:,} bytes")
    table.add_row("Destination", str(saved_path.resolve()))
    console.print(table)


@cli.command("send-invoice")
@click.option("--invoice", "-i", "identifier", required=True, help="Invoice DocNumber, QBO ID, or Order ID")
@click.option("--to", "recipient_email", default=None, help="Recipient email address (defaults to customer email)")
@click.option("--subject", "-s", default=None, help="Custom email subject")
@click.option("--mock/--no-mock", default=None, help="Force mock sandbox or live SMTP mode")
def send_invoice_cmd(identifier: str, recipient_email: Optional[str], subject: Optional[str], mock: Optional[bool]):
    """Dispatch invoice email with vector PDF attachment via SMTP or sandbox mock."""
    _, ledger, _, _, cfg = get_components()
    inv = (
        ledger.get_invoice_by_id(identifier)
        or ledger.get_invoice_by_doc_number(identifier)
        or ledger.get_invoice_by_order_id(identifier)
    )
    if not inv:
        console.print(f"[bold red][ERROR][/bold red] Invoice '{identifier}' not found in local ledger.")
        return

    if mock is not None:
        cfg.mail_use_mock = mock

    mailer = InvoiceMailer(settings=cfg, ledger=ledger)
    target_email = recipient_email or inv.customer_email
    if not target_email:
        console.print(f"[bold red][ERROR][/bold red] No recipient email specified and none on file for customer.")
        return

    with console.status(f"[bold green]Generating PDF and dispatching email to {target_email}..."):
        try:
            dispatch = mailer.send_invoice_email(
                invoice=inv,
                recipient_email=target_email,
                subject=subject,
            )
        except Exception as exc:
            console.print(f"[bold red][ERROR][/bold red] Failed to send email: {exc}")
            return

    console.print(f"[bold green][OK][/bold green] Email successfully dispatched ({dispatch.status})!")
    table = Table(title=f"Invoice Dispatch Audit: {inv.doc_number}", show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("Dispatch ID", str(dispatch.id))
    table.add_row("Recipient", dispatch.recipient_email)
    table.add_row("Subject", dispatch.subject)
    table.add_row("Status", f"[bold green]{dispatch.status}[/bold green]")
    table.add_row("Attachment", "Invoice PDF (Vector + QR)")
    table.add_row("Timestamp", dispatch.sent_at.isoformat())
    console.print(table)


if __name__ == "__main__":
    cli()


