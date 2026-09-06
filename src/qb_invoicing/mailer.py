"""
Invoice Email Dispatch Engine with Vector PDF Attachments and SMTP Sandbox.
"""

from __future__ import annotations

import smtplib
from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional, Tuple

from qb_invoicing.config import Settings, settings as default_settings
from qb_invoicing.ledger import LedgerRepository
from qb_invoicing.models import EmailDispatchRecord, InvoiceRecord
from qb_invoicing.pdf_generator import InvoicePDFGenerator


class InvoiceMailer:
    """
    Assembles and dispatches invoice emails with attached vector PDFs,
    supporting live TLS-secured SMTP servers and zero-dependency mock testing.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        ledger: Optional[LedgerRepository] = None,
        pdf_generator: Optional[InvoicePDFGenerator] = None,
    ):
        self.settings = settings or default_settings
        self.ledger = ledger or LedgerRepository(self.settings.database_path)
        self.pdf_generator = pdf_generator or InvoicePDFGenerator(self.settings)

    def generate_default_email_content(
        self,
        invoice: InvoiceRecord,
        payment_url: str,
    ) -> Tuple[str, str, str]:
        """
        Generate standard professional subject, plain text body, and responsive HTML body.
        Returns (subject, text_body, html_body).
        """
        subject = f"Invoice {invoice.doc_number} from {self.settings.company_name}"
        due_str = invoice.due_date or invoice.txn_date
        bal_str = f"${invoice.balance_due:,.2f} {invoice.currency}"
        tot_str = f"${invoice.total_amount:,.2f} {invoice.currency}"

        text_body = (
            f"Dear {invoice.customer_name},\n\n"
            f"Thank you for your business. Please find attached invoice {invoice.doc_number} "
            f"for {tot_str}.\n\n"
            f"Invoice Summary:\n"
            f"- Invoice Number: {invoice.doc_number}\n"
            f"- Issue Date: {invoice.txn_date}\n"
            f"- Due Date: {due_str}\n"
            f"- Outstanding Balance: {bal_str}\n\n"
            f"You can pay online immediately via Credit Card, ACH, Apple Pay, or Google Pay at:\n"
            f"{payment_url}\n\n"
            f"If you have any questions, feel free to contact us at {self.settings.company_email}.\n\n"
            f"Sincerely,\n"
            f"{self.settings.company_name}\n"
            f"{self.settings.company_phone}"
        )

        html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px; color: #1e293b; }}
    .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 10px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }}
    .header {{ background: #1e3a8a; padding: 24px; color: #ffffff; text-align: center; }}
    .header h1 {{ margin: 0; font-size: 20px; font-weight: 700; }}
    .content {{ padding: 28px; }}
    .details-box {{ background: #f1f5f9; border-radius: 8px; padding: 18px; margin: 20px 0; }}
    .row {{ display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #e2e8f0; }}
    .row:last-child {{ border-bottom: none; }}
    .btn {{ display: block; width: 220px; margin: 24px auto; background: #2563eb; color: #ffffff !important; text-align: center; padding: 14px 20px; border-radius: 6px; font-weight: 600; text-decoration: none; font-size: 15px; }}
    .footer {{ background: #f8fafc; padding: 18px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>{self.settings.company_name}</h1>
    </div>
    <div class="content">
      <p>Dear <strong>{invoice.customer_name}</strong>,</p>
      <p>Thank you for your business. Please find attached invoice <strong>{invoice.doc_number}</strong>.</p>
      
      <div class="details-box">
        <table width="100%" style="font-size: 14px; border-collapse: collapse;">
          <tr>
            <td style="padding: 6px 0; color: #64748b;">Invoice Number:</td>
            <td style="padding: 6px 0; text-align: right; font-weight: 600;">{invoice.doc_number}</td>
          </tr>
          <tr>
            <td style="padding: 6px 0; color: #64748b;">Issue Date:</td>
            <td style="padding: 6px 0; text-align: right;">{invoice.txn_date}</td>
          </tr>
          <tr>
            <td style="padding: 6px 0; color: #64748b;">Due Date:</td>
            <td style="padding: 6px 0; text-align: right;">{due_str}</td>
          </tr>
          <tr>
            <td style="padding: 6px 0; color: #64748b;">Total Amount:</td>
            <td style="padding: 6px 0; text-align: right; font-weight: 600;">{tot_str}</td>
          </tr>
          <tr style="border-top: 2px solid #cbd5e1;">
            <td style="padding: 8px 0; font-weight: bold; color: #1e3a8a;">Balance Due:</td>
            <td style="padding: 8px 0; text-align: right; font-weight: bold; color: #1e3a8a; font-size: 16px;">{bal_str}</td>
          </tr>
        </table>
      </div>

      <a href="{payment_url}" class="btn">Pay Online Now &rarr;</a>

      <p style="font-size: 13px; color: #64748b; text-align: center;">
        A copy of your PDF invoice with a mobile payment QR code is attached to this email.
      </p>
    </div>
    <div class="footer">
      Questions? Contact {self.settings.company_email} or {self.settings.company_phone}.<br />
      &copy; {datetime.now(timezone.utc).year} {self.settings.company_name}. All rights reserved.
    </div>
  </div>
</body>
</html>
"""
        return subject, text_body, html_body

    def build_mime_message(
        self,
        invoice: InvoiceRecord,
        recipient_email: str,
        subject: str,
        text_body: str,
        html_body: str,
        pdf_bytes: bytes,
    ) -> MIMEMultipart:
        """Construct standard multipart/mixed email with multipart/alternative body and PDF attachment."""
        msg = MIMEMultipart("mixed")
        msg["From"] = self.settings.mail_from
        msg["To"] = recipient_email
        msg["Subject"] = subject
        msg["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

        # Alternative container for text and HTML parts
        body_part = MIMEMultipart("alternative")
        body_part.attach(MIMEText(text_body, "plain", "utf-8"))
        body_part.attach(MIMEText(html_body, "html", "utf-8"))
        msg.attach(body_part)

        # PDF Attachment
        pdf_attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
        filename = f"Invoice_{invoice.doc_number}.pdf"
        pdf_attachment.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(pdf_attachment)

        return msg

    def send_invoice_email(
        self,
        invoice: InvoiceRecord,
        recipient_email: Optional[str] = None,
        subject: Optional[str] = None,
        text_body: Optional[str] = None,
        html_body: Optional[str] = None,
        pdf_bytes: Optional[bytes] = None,
        payment_url: Optional[str] = None,
    ) -> EmailDispatchRecord:
        """
        Dispatches invoice email with vector PDF attachment.
        If in mock mode (mail_use_mock=True), dispatches without connecting to an external SMTP server.
        """
        target_recipient = recipient_email or invoice.customer_email
        if not target_recipient:
            raise ValueError(f"No recipient email address found for invoice {invoice.doc_number}")

        # Resolve Payment URL
        if not payment_url:
            portal = self.settings.payment_portal_url.rstrip("/")
            if "/pay" in portal:
                payment_url = f"{portal}/{invoice.qbo_invoice_id}"
            else:
                payment_url = f"{portal}/pay/{invoice.qbo_invoice_id}"

        # Resolve content
        def_subj, def_txt, def_html = self.generate_default_email_content(invoice, payment_url)
        final_subject = subject or def_subj
        final_text = text_body or def_txt
        final_html = html_body or def_html

        # Generate PDF bytes if not provided
        if pdf_bytes is None:
            pdf_bytes = self.pdf_generator.generate_pdf_bytes(invoice, payment_url=payment_url)

        # Build MIME Message
        mime_msg = self.build_mime_message(
            invoice=invoice,
            recipient_email=target_recipient,
            subject=final_subject,
            text_body=final_text,
            html_body=final_html,
            pdf_bytes=pdf_bytes,
        )

        status = "SENT"
        error_msg: Optional[str] = None

        if self.settings.mail_use_mock:
            # Mock mode: Validate payload and simulate successful transmission
            status = "SIMULATED"
        else:
            # Live SMTP transmission
            try:
                server = smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=15)
                if self.settings.smtp_use_tls:
                    server.starttls()
                if self.settings.smtp_user and self.settings.smtp_password:
                    server.login(self.settings.smtp_user, self.settings.smtp_password)
                server.send_message(mime_msg)
                server.quit()
                status = "SENT"
            except Exception as exc:
                status = "FAILED"
                error_msg = str(exc)

        # Record in audit ledger
        dispatch_record = EmailDispatchRecord(
            invoice_id=invoice.qbo_invoice_id,
            doc_number=invoice.doc_number,
            recipient_email=target_recipient,
            subject=final_subject,
            sent_at=datetime.now(timezone.utc),
            status=status,
            has_attachment=True,
            error_message=error_msg,
            created_at=datetime.now(timezone.utc),
        )

        record_id = self.ledger.record_email_dispatch(dispatch_record)
        dispatch_record.id = record_id

        if status == "FAILED":
            raise RuntimeError(f"Failed to dispatch email via SMTP: {error_msg}")

        return dispatch_record
