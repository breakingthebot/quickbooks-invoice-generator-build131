"""
Automated Dunning & Overdue Payment Aging Engine for QuickBooks Invoices.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from qb_invoicing.config import Settings, settings as default_settings
from qb_invoicing.ledger import LedgerRepository
from qb_invoicing.models import (
    AgingBucket,
    AgingBucketInvoice,
    AgingScheduleReport,
    DunningBatchResult,
    DunningLevel,
    DunningNoticeRecord,
    InvoiceRecord,
    PaymentStatus,
)


def get_escalation_level(days_overdue: int) -> Optional[Tuple[DunningLevel, str]]:
    """Determine escalation tier and descriptive title based on days overdue."""
    if days_overdue <= 0:
        return None
    elif 1 <= days_overdue <= 14:
        return DunningLevel.FRIENDLY, "Friendly Reminder"
    elif 15 <= days_overdue <= 30:
        return DunningLevel.URGENT, "Urgent Notice"
    elif 31 <= days_overdue <= 60:
        return DunningLevel.FINAL_DEMAND, "Final Demand"
    else:
        return DunningLevel.COLLECTIONS, "Collections Warning"


def generate_dunning_content(
    invoice: InvoiceRecord,
    level: DunningLevel,
    level_name: str,
    days_overdue: int,
    company_name: str,
    company_email: str,
    company_phone: str,
    portal_url: str,
) -> Tuple[str, str, str]:
    """
    Generate professional email subject, plain text body, and responsive HTML body.
    Returns (subject, text_body, html_body).
    """
    inv_num = invoice.doc_number
    cust = invoice.customer_name
    bal_str = f"${invoice.balance_due:,.2f} {invoice.currency}"
    due_date = invoice.due_date or invoice.txn_date
    if "/pay" in portal_url:
        pay_link = f"{portal_url.rstrip('/')}/{invoice.qbo_invoice_id}"
    else:
        pay_link = f"{portal_url.rstrip('/')}/pay/{invoice.qbo_invoice_id}"

    # Escalation theme color & styling
    if level == DunningLevel.FRIENDLY:
        subject = f"Friendly Payment Reminder: Invoice {inv_num} is past due"
        badge_color = "#3b82f6"  # Blue
        header_text = "Friendly Payment Reminder"
        message_intro = (
            f"This is a courteous reminder that invoice <strong>{inv_num}</strong> was due on "
            f"<strong>{due_date}</strong> and currently shows an outstanding balance of <strong>{bal_str}</strong>. "
            "We kindly request that you review the statement and remit payment at your earliest convenience."
        )
    elif level == DunningLevel.URGENT:
        subject = f"Urgent Notice: Overdue Balance for Invoice {inv_num} ({days_overdue} days past due)"
        badge_color = "#f59e0b"  # Amber
        header_text = "Urgent: Overdue Balance Notice"
        message_intro = (
            f"Our accounting records indicate that invoice <strong>{inv_num}</strong> is now "
            f"<strong>{days_overdue} days overdue</strong>. The outstanding balance is <strong>{bal_str}</strong>. "
            "Prompt settlement is required to ensure uninterrupted service."
        )
    elif level == DunningLevel.FINAL_DEMAND:
        subject = f"Final Demand Notice: Immediate Payment Required for Invoice {inv_num}"
        badge_color = "#ea580c"  # Orange
        header_text = "Final Demand for Payment"
        message_intro = (
            f"Despite our previous notifications, invoice <strong>{inv_num}</strong> remains unpaid and is now "
            f"<strong>{days_overdue} days past due</strong>. The outstanding amount is <strong>{bal_str}</strong>. "
            "Please remit payment immediately to avoid suspension of services and further recovery escalation."
        )
    else:  # COLLECTIONS
        subject = f"Pre-Collections Notice: Account Suspension Pending for Invoice {inv_num}"
        badge_color = "#dc2626"  # Red
        header_text = "Pre-Collections Formal Notice"
        message_intro = (
            f"This is a formal escalation regarding seriously delinquent invoice <strong>{inv_num}</strong> "
            f"({days_overdue} days overdue). Total amount due: <strong>{bal_str}</strong>. "
            "Failure to settle this liability within 5 business days will result in referral to an external collection agency."
        )

    # Plain-text template
    text_body = f"""Dear {cust},

[{header_text}]
Invoice Number: {inv_num}
QuickBooks ID: {invoice.qbo_invoice_id}
Original Due Date: {due_date}
Days Overdue: {days_overdue}
Outstanding Balance: {bal_str}

{message_intro.replace('<strong>', '').replace('</strong>', '')}

Please remit payment promptly:
Online Portal: {pay_link}

If you have already sent payment or have billing questions, please contact our accounts department immediately:
Email: {company_email}
Phone: {company_phone}

Thank you,
{company_name} Accounting Team
"""

    # Responsive HTML template
    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{subject}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; color: #1e293b; margin: 0; padding: 24px; }}
    .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }}
    .header {{ background-color: {badge_color}; color: #ffffff; padding: 24px; text-align: center; }}
    .header h1 {{ margin: 0; font-size: 20px; font-weight: 700; }}
    .content {{ padding: 32px 24px; }}
    .badge {{ display: inline-block; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: 700; text-transform: uppercase; background-color: #f1f5f9; color: #334155; margin-bottom: 16px; }}
    .summary-card {{ background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 16px; margin: 20px 0; }}
    .summary-row {{ display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 14px; }}
    .summary-row.total {{ font-size: 18px; font-weight: 700; color: #0f172a; border-top: 1px solid #cbd5e1; padding-top: 8px; margin-top: 8px; }}
    .btn {{ display: inline-block; background-color: {badge_color}; color: #ffffff !important; text-decoration: none; padding: 12px 28px; border-radius: 6px; font-weight: 600; font-size: 15px; margin: 16px 0; text-align: center; }}
    .footer {{ padding: 16px 24px; background-color: #f1f5f9; font-size: 12px; color: #64748b; text-align: center; border-top: 1px solid #e2e8f0; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>{header_text}</h1>
    </div>
    <div class="content">
      <p>Dear {cust},</p>
      <p>{message_intro}</p>
      
      <div class="summary-card">
        <div class="summary-row"><span>Invoice Number:</span> <strong>{inv_num}</strong></div>
        <div class="summary-row"><span>Original Due Date:</span> <strong>{due_date}</strong></div>
        <div class="summary-row"><span>Days Overdue:</span> <strong style="color: {badge_color};">{days_overdue} days</strong></div>
        <div class="summary-row total"><span>Total Amount Due:</span> <span>{bal_str}</span></div>
      </div>

      <div style="text-align: center;">
        <a href="{pay_link}" class="btn">Pay Invoice Online</a>
      </div>

      <p style="font-size: 13px; color: #64748b; margin-top: 24px;">
        If you have already sent this payment, please disregard this notice or contact our accounts team to confirm receipt.
      </p>
    </div>
    <div class="footer">
      <p><strong>{company_name}</strong> &bull; {company_email} &bull; {company_phone}</p>
      <p>This is an automated dunning statement for QuickBooks Invoice #{invoice.qbo_invoice_id}.</p>
    </div>
  </div>
</body>
</html>
"""
    return subject, text_body, html_body


class DunningEngine:
    """
    Evaluates accounts receivable aging, calculates overdue escalation tiers,
    applies cooldown frequency caps, and dispatches automated notices.
    """

    def __init__(
        self,
        ledger: Optional[LedgerRepository] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or default_settings
        self.ledger = ledger or LedgerRepository(self.settings.database_path)

    def get_aging_schedule(self, as_of_date: Optional[str] = None) -> AgingScheduleReport:
        """Fetch the current accounts receivable aging buckets report."""
        return self.ledger.get_aging_report(as_of_date=as_of_date)

    def evaluate_invoice(
        self,
        invoice_id: str,
        as_of_date: Optional[str] = None,
        cooldown_days: Optional[int] = None,
        force: bool = False,
    ) -> Optional[DunningNoticeRecord]:
        """
        Evaluate a single invoice for dunning notice generation.
        Returns DunningNoticeRecord if eligible, or None if current/paid or in cooldown.
        """
        inv = self.ledger.get_invoice(invoice_id)
        if not inv:
            return None

        # Check balance and status
        if inv.balance_due <= Decimal("0.001") or inv.payment_status in (
            PaymentStatus.PAID,
            PaymentStatus.VOIDED,
        ):
            return None

        if as_of_date:
            try:
                ref_date = datetime.strptime(as_of_date, "%Y-%m-%d").date()
            except ValueError:
                ref_date = datetime.now(timezone.utc).date()
        else:
            ref_date = datetime.now(timezone.utc).date()

        due_date_str = inv.due_date or inv.txn_date
        try:
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
        except ValueError:
            due_date = ref_date

        days_overdue = (ref_date - due_date).days
        if days_overdue <= 0:
            return None  # Current, not overdue

        tier_info = get_escalation_level(days_overdue)
        if not tier_info:
            return None

        level, level_name = tier_info

        # Check cooldown period against previous notices
        cooldown = cooldown_days if cooldown_days is not None else self.settings.dunning_cooldown_days
        if not force and cooldown > 0:
            last_notice = self.ledger.get_last_dunning_notice(inv.qbo_invoice_id)
            if last_notice:
                time_since_notice = datetime.now(timezone.utc) - last_notice.sent_at
                if time_since_notice < timedelta(days=cooldown):
                    return None  # Cooldown active, suppress notice

        subject, text_body, html_body = generate_dunning_content(
            invoice=inv,
            level=level,
            level_name=level_name,
            days_overdue=days_overdue,
            company_name=self.settings.company_name,
            company_email=self.settings.company_email,
            company_phone=self.settings.company_phone,
            portal_url=self.settings.payment_portal_url,
        )

        return DunningNoticeRecord(
            invoice_id=inv.qbo_invoice_id,
            doc_number=inv.doc_number,
            customer_name=inv.customer_name,
            customer_email=inv.customer_email,
            escalation_level=level.value,
            level_name=level_name,
            days_overdue=days_overdue,
            balance_due=inv.balance_due,
            subject=subject,
            sent_at=datetime.now(timezone.utc),
            status="SENT",
            body_preview=text_body[:280] + ("..." if len(text_body) > 280 else ""),
        )

    def run_dunning_cycle(
        self,
        as_of_date: Optional[str] = None,
        cooldown_days: Optional[int] = None,
        force: bool = False,
        dry_run: bool = False,
    ) -> DunningBatchResult:
        """
        Execute automated dunning evaluation across all open invoices.
        Dispatches notices, applies cooldown filtering, and updates history.
        """
        if as_of_date:
            try:
                ref_date = datetime.strptime(as_of_date, "%Y-%m-%d").date()
            except ValueError:
                ref_date = datetime.now(timezone.utc).date()
        else:
            ref_date = datetime.now(timezone.utc).date()

        cooldown = cooldown_days if cooldown_days is not None else self.settings.dunning_cooldown_days

        # Fetch open invoices
        open_invoices = self.ledger.list_invoices(limit=500)
        evaluated_count = 0
        current_count = 0
        skipped_cooldown = 0
        notices_to_record: List[DunningNoticeRecord] = []

        for inv in open_invoices:
            if inv.balance_due <= Decimal("0.001") or inv.payment_status in (
                PaymentStatus.PAID,
                PaymentStatus.VOIDED,
            ):
                continue

            evaluated_count += 1
            due_date_str = inv.due_date or inv.txn_date
            try:
                due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
            except ValueError:
                due_date = ref_date

            days_overdue = (ref_date - due_date).days
            if days_overdue <= 0:
                current_count += 1
                continue

            # Check cooldown
            if not force and cooldown > 0:
                last_notice = self.ledger.get_last_dunning_notice(inv.qbo_invoice_id)
                if last_notice:
                    diff = datetime.now(timezone.utc) - last_notice.sent_at
                    if diff < timedelta(days=cooldown):
                        skipped_cooldown += 1
                        continue

            tier_info = get_escalation_level(days_overdue)
            if not tier_info:
                continue

            level, level_name = tier_info
            subject, text_body, _ = generate_dunning_content(
                invoice=inv,
                level=level,
                level_name=level_name,
                days_overdue=days_overdue,
                company_name=self.settings.company_name,
                company_email=self.settings.company_email,
                company_phone=self.settings.company_phone,
                portal_url=self.settings.payment_portal_url,
            )

            status = "SIMULATED" if dry_run else "SENT"
            notice = DunningNoticeRecord(
                invoice_id=inv.qbo_invoice_id,
                doc_number=inv.doc_number,
                customer_name=inv.customer_name,
                customer_email=inv.customer_email,
                escalation_level=level.value,
                level_name=level_name,
                days_overdue=days_overdue,
                balance_due=inv.balance_due,
                subject=subject,
                sent_at=datetime.now(timezone.utc),
                status=status,
                body_preview=text_body[:280] + ("..." if len(text_body) > 280 else ""),
            )

            if not dry_run:
                rec_id = self.ledger.record_dunning_notice(notice)
                notice.id = rec_id

            notices_to_record.append(notice)

        return DunningBatchResult(
            evaluated_count=evaluated_count,
            notices_sent_count=len(notices_to_record),
            skipped_cooldown_count=skipped_cooldown,
            current_count=current_count,
            notices=notices_to_record,
        )
