"""
Vector PDF Invoice Generator with Embedded Instant Payment QR Codes.
"""

from __future__ import annotations

import io
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from qb_invoicing.config import Settings, settings as default_settings
from qb_invoicing.models import InvoiceRecord, OrderData, PaymentStatus


def generate_payment_qr(url: str, box_size: int = 6, border: int = 2) -> bytes:
    """
    Generate high-contrast, scannable QR code image bytes (PNG format).
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0F172A", back_color="#FFFFFF")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


class InvoicePDFGenerator:
    """
    Renders audit-compliant, high-resolution vector PDF invoices
    featuring itemized line tables, tax/shipping breakdowns,
    and mobile-scannable instant payment QR codes.
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or default_settings

    def _get_status_colors(self, status: PaymentStatus) -> Tuple[colors.Color, colors.Color]:
        """Returns (background_color, text_color) for status badges."""
        if status == PaymentStatus.PAID:
            return colors.HexColor("#DCFCE7"), colors.HexColor("#15803D")
        elif status == PaymentStatus.PARTIAL:
            return colors.HexColor("#FEF3C7"), colors.HexColor("#B45309")
        elif status == PaymentStatus.OVERDUE:
            return colors.HexColor("#FEE2E2"), colors.HexColor("#B91C1C")
        elif status == PaymentStatus.VOIDED:
            return colors.HexColor("#F3F4F6"), colors.HexColor("#4B5563")
        else:  # PENDING
            return colors.HexColor("#DBEAFE"), colors.HexColor("#1D4ED8")

    def _extract_line_items(
        self, invoice: InvoiceRecord, order: Optional[OrderData] = None
    ) -> Tuple[List[Dict[str, Any]], Decimal, Decimal, Decimal]:
        """
        Extract line items, subtotal, tax, and shipping from order or invoice raw_payload.
        Returns (items_list, subtotal, tax_amount, shipping_amount).
        """
        items: List[Dict[str, Any]] = []
        subtotal = Decimal("0.00")
        tax_amount = Decimal("0.00")
        shipping_amount = Decimal("0.00")

        # 1. Try from order object
        if order and order.items:
            for it in order.items:
                net_line = it.net_line_total
                subtotal += net_line
                items.append({
                    "name": it.name,
                    "description": it.description or "",
                    "quantity": float(it.quantity),
                    "unit_price": float(it.unit_price),
                    "amount": float(net_line),
                    "tax_code": it.tax_code,
                })
            tax_amount = getattr(order, "computed_tax", Decimal("0.00"))
            shipping_amount = getattr(order, "shipping_fee", Decimal("0.00"))
            return items, subtotal, tax_amount, shipping_amount

        # 2. Try from invoice.raw_payload
        if invoice.raw_payload:
            try:
                payload = json.loads(invoice.raw_payload)
                raw_lines = payload.get("Line", [])
                for line in raw_lines:
                    detail_type = line.get("DetailType")
                    amt = Decimal(str(line.get("Amount", 0.0)))
                    desc = line.get("Description", "Item")

                    if detail_type == "SalesItemLineDetail":
                        detail = line.get("SalesItemLineDetail", {})
                        item_ref = detail.get("ItemRef", {})
                        name = item_ref.get("name", desc)
                        qty = float(detail.get("Qty", 1.0))
                        price = float(detail.get("UnitPrice", amt))
                        tax_code = detail.get("TaxCodeRef", {}).get("value", "TAX")

                        if item_ref.get("value") == "SHIPPING" or "shipping" in desc.lower():
                            shipping_amount += amt
                        else:
                            subtotal += amt
                            items.append({
                                "name": name,
                                "description": desc if desc != name else "",
                                "quantity": qty,
                                "unit_price": price,
                                "amount": float(amt),
                                "tax_code": tax_code,
                            })
                # If subtotal is still 0 but we have total_amount, calculate
                if not items:
                    items.append({
                        "name": f"Invoice {invoice.doc_number}",
                        "description": "Professional services / goods rendered",
                        "quantity": 1.0,
                        "unit_price": float(invoice.total_amount),
                        "amount": float(invoice.total_amount),
                        "tax_code": "TAX",
                    })
                    subtotal = invoice.total_amount
                return items, subtotal, tax_amount, shipping_amount
            except Exception:
                pass

        # 3. Fallback default single line item
        items.append({
            "name": f"Invoice {invoice.doc_number}",
            "description": "Professional goods and services rendered",
            "quantity": 1.0,
            "unit_price": float(invoice.total_amount),
            "amount": float(invoice.total_amount),
            "tax_code": "TAX",
        })
        subtotal = invoice.total_amount
        return items, subtotal, tax_amount, shipping_amount

    def generate_pdf_bytes(
        self,
        invoice: InvoiceRecord,
        payment_url: Optional[str] = None,
        order: Optional[OrderData] = None,
    ) -> bytes:
        """
        Render the invoice into an in-memory PDF byte buffer.
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        styles = getSampleStyleSheet()
        normal = styles["Normal"]
        normal.textColor = colors.HexColor("#0F172A")
        normal.fontSize = 9
        normal.leading = 12

        title_style = ParagraphStyle(
            "InvoiceTitle",
            parent=normal,
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#1E3A8A"),
            alignment=2,  # Right aligned
        )

        company_title_style = ParagraphStyle(
            "CompanyTitle",
            parent=normal,
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#0F172A"),
        )

        meta_label_style = ParagraphStyle(
            "MetaLabel",
            parent=normal,
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#64748B"),
        )

        meta_val_style = ParagraphStyle(
            "MetaVal",
            parent=normal,
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#0F172A"),
        )

        th_style = ParagraphStyle(
            "TableHeader",
            parent=normal,
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=colors.white,
        )

        th_right_style = ParagraphStyle(
            "TableHeaderRight",
            parent=th_style,
            alignment=2,
        )

        td_style = ParagraphStyle(
            "TableCell",
            parent=normal,
            fontName="Helvetica",
            fontSize=9,
            leading=12,
        )

        td_bold_style = ParagraphStyle(
            "TableCellBold",
            parent=td_style,
            fontName="Helvetica-Bold",
        )

        td_right_style = ParagraphStyle(
            "TableCellRight",
            parent=td_style,
            alignment=2,
        )

        elements: List[Any] = []

        # --- Resolve Payment URL ---
        if not payment_url:
            portal = self.settings.payment_portal_url.rstrip("/")
            if "/pay" in portal:
                payment_url = f"{portal}/{invoice.qbo_invoice_id}"
            else:
                payment_url = f"{portal}/pay/{invoice.qbo_invoice_id}"

        # --- 1. Header Section (Company & Invoice Title) ---
        company_info = [
            Paragraph(self.settings.company_name, company_title_style),
            Spacer(1, 4),
            Paragraph(f"<b>Email:</b> {self.settings.company_email}", normal),
            Paragraph(f"<b>Phone:</b> {self.settings.company_phone}", normal),
            Paragraph(f"<b>Portal:</b> {payment_url}", normal),
        ]

        bg_col, txt_col = self._get_status_colors(invoice.payment_status)
        badge_html = (
            f'<font color="{txt_col.hexval()}"><b>'
            f'&nbsp;{invoice.payment_status.value.upper()}&nbsp;'
            f'</b></font>'
        )

        invoice_meta = [
            Paragraph("INVOICE", title_style),
            Spacer(1, 4),
            Paragraph(
                f'<table width="100%">'
                f'<tr><td align="right"><b>Invoice #:</b></td><td align="right">{invoice.doc_number}</td></tr>'
                f'<tr><td align="right"><b>Status:</b></td><td align="right">{badge_html}</td></tr>'
                f'<tr><td align="right"><b>Date:</b></td><td align="right">{invoice.txn_date}</td></tr>'
                f'<tr><td align="right"><b>Due Date:</b></td><td align="right">{invoice.due_date or invoice.txn_date}</td></tr>'
                f'<tr><td align="right"><b>Order Ref:</b></td><td align="right">{invoice.order_id}</td></tr>'
                f'</table>',
                ParagraphStyle("InvoiceMetaRight", parent=normal, alignment=2, leading=14),
            ),
        ]

        header_table = Table(
            [[company_info, invoice_meta]],
            colWidths=[310, 230],
        )
        header_table.setStyle(
            TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ])
        )
        elements.append(header_table)
        elements.append(Spacer(1, 14))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E2E8F0"), spaceAfter=14))

        # --- 2. Bill To / Ship To / Payment Details Grid ---
        bill_to = [
            Paragraph("BILLED TO", meta_label_style),
            Spacer(1, 2),
            Paragraph(f"<b>{invoice.customer_name}</b>", meta_val_style),
            Paragraph(invoice.customer_email or "No email provided", meta_val_style),
        ]
        if order and order.customer and order.customer.billing_address:
            addr = order.customer.billing_address
            bill_to.append(Paragraph(f"{addr.line1}", meta_val_style))
            if addr.line2:
                bill_to.append(Paragraph(f"{addr.line2}", meta_val_style))
            bill_to.append(Paragraph(f"{addr.city}, {addr.state} {addr.postal_code}", meta_val_style))
            bill_to.append(Paragraph(f"{addr.country}", meta_val_style))

        ship_to = [
            Paragraph("PAYMENT TERMS", meta_label_style),
            Spacer(1, 2),
            Paragraph(f"Net {self.settings.default_payment_terms_days} Days", meta_val_style),
            Spacer(1, 6),
            Paragraph("CURRENCY", meta_label_style),
            Spacer(1, 2),
            Paragraph(f"{invoice.currency.upper()}", meta_val_style),
        ]

        client_grid = Table(
            [[bill_to, ship_to]],
            colWidths=[310, 230],
        )
        client_grid.setStyle(
            TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ])
        )
        elements.append(client_grid)
        elements.append(Spacer(1, 14))

        # --- 3. Line Items Table ---
        items, subtotal, tax_amt, ship_amt = self._extract_line_items(invoice, order)

        table_rows = [
            [
                Paragraph("#", th_style),
                Paragraph("Description", th_style),
                Paragraph("Qty", th_right_style),
                Paragraph("Unit Rate", th_right_style),
                Paragraph("Tax", th_right_style),
                Paragraph("Amount", th_right_style),
            ]
        ]

        for idx, it in enumerate(items, start=1):
            name_p = Paragraph(f"<b>{it['name']}</b>", td_style)
            if it.get("description"):
                desc_p = Paragraph(f"<font color='#64748B' size=8>{it['description']}</font>", td_style)
                item_cell = [name_p, desc_p]
            else:
                item_cell = [name_p]

            qty_str = f"{it['quantity']:g}"
            rate_str = f"${it['unit_price']:,.2f}"
            tax_code = it.get("tax_code", "TAX")
            amount_str = f"${it['amount']:,.2f}"

            table_rows.append([
                Paragraph(str(idx), td_style),
                item_cell,
                Paragraph(qty_str, td_right_style),
                Paragraph(rate_str, td_right_style),
                Paragraph(tax_code, td_right_style),
                Paragraph(amount_str, td_right_style),
            ])

        # Widths total: 540pt (letter width is 612 - 72 = 540)
        col_widths = [28, 252, 45, 75, 50, 90]
        items_table = Table(table_rows, colWidths=col_widths, repeatRows=1)

        t_style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
            ("ALIGN", (0, 0), (1, -1), "LEFT"),
            ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ]

        for i in range(1, len(table_rows)):
            if i % 2 == 0:
                t_style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F8FAFC")))

        items_table.setStyle(TableStyle(t_style))
        elements.append(items_table)
        elements.append(Spacer(1, 14))

        # --- 4. Totals & Embedded QR Code Section ---
        qr_bytes = generate_payment_qr(payment_url, box_size=5, border=1)
        qr_img_stream = io.BytesIO(qr_bytes)
        qr_flowable = Image(qr_img_stream, width=88, height=88)

        qr_box = [
            Table(
                [[
                    qr_flowable,
                    [
                        Paragraph("<b>Scan to Pay Online</b>", ParagraphStyle("QRTxtHead", parent=normal, fontName="Helvetica-Bold", fontSize=10, textColor=colors.HexColor("#1E3A8A"))),
                        Spacer(1, 3),
                        Paragraph("Scan this QR code with your mobile camera to pay immediately via Credit Card, ACH, Apple Pay, or Google Pay.", ParagraphStyle("QRTxt", parent=normal, fontSize=8, leading=11, textColor=colors.HexColor("#475569"))),
                        Spacer(1, 4),
                        Paragraph(f"<font color='#2563EB' size=8><u>{payment_url}</u></font>", ParagraphStyle("QRUrl", parent=normal, fontSize=8, leading=10)),
                    ],
                ]],
                colWidths=[96, 174],
            )
        ]
        qr_box[0].setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ]))

        # Calculate totals
        paid_amount = invoice.total_amount - invoice.balance_due
        if paid_amount < Decimal("0.00"):
            paid_amount = Decimal("0.00")

        totals_data = [
            [Paragraph("Subtotal:", td_bold_style), Paragraph(f"${subtotal:,.2f}", td_right_style)],
        ]
        if tax_amt > Decimal("0.00"):
            totals_data.append([Paragraph("Tax:", td_bold_style), Paragraph(f"${tax_amt:,.2f}", td_right_style)])
        if ship_amt > Decimal("0.00"):
            totals_data.append([Paragraph("Shipping:", td_bold_style), Paragraph(f"${ship_amt:,.2f}", td_right_style)])

        totals_data.append([Paragraph("Total Invoiced:", td_bold_style), Paragraph(f"<b>${invoice.total_amount:,.2f}</b>", td_right_style)])
        totals_data.append([Paragraph("Amount Paid:", td_bold_style), Paragraph(f"<font color='#15803D'>-${paid_amount:,.2f}</font>", td_right_style)])
        
        # Balance Due Box
        bal_bg = "#FEE2E2" if invoice.payment_status == PaymentStatus.OVERDUE else "#EEF2F6"
        bal_color = "#B91C1C" if invoice.payment_status == PaymentStatus.OVERDUE else "#1E3A8A"

        totals_data.append([
            Paragraph(f"<font color='{bal_color}'><b>Balance Due ({invoice.currency.upper()}):</b></font>", td_bold_style),
            Paragraph(f"<font color='{bal_color}' size=11><b>${invoice.balance_due:,.2f}</b></font>", td_right_style),
        ])

        totals_table = Table(totals_data, colWidths=[140, 110])
        totals_table.setStyle(TableStyle([
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, -2), (1, -2), 0.5, colors.HexColor("#CBD5E1")),
            ("BACKGROUND", (0, -1), (1, -1), colors.HexColor(bal_bg)),
            ("BOX", (0, -1), (1, -1), 1, colors.HexColor(bal_color)),
        ]))

        bottom_grid = Table(
            [[qr_box, totals_table]],
            colWidths=[280, 260],
        )
        bottom_grid.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        elements.append(KeepTogether([bottom_grid]))

        # --- 5. Footer / Payment Notes ---
        elements.append(Spacer(1, 24))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E2E8F0"), spaceAfter=8))
        footer_text = (
            f"<b>Payment Instructions:</b> Remit payments online via credit card/ACH at {payment_url} "
            f"or scan the QR code above. Inquiries may be directed to {self.settings.company_email} or {self.settings.company_phone}. "
            f"<br/>Thank you for your business!"
        )
        elements.append(Paragraph(footer_text, ParagraphStyle("FooterP", parent=normal, fontSize=8, leading=11, textColor=colors.HexColor("#64748B"), alignment=1)))

        doc.build(elements)
        return buffer.getvalue()

    def save_pdf(
        self,
        invoice: InvoiceRecord,
        output_path: Optional[str | Path] = None,
        payment_url: Optional[str] = None,
        order: Optional[OrderData] = None,
    ) -> Path:
        """
        Render and write invoice PDF to a filesystem path.
        Defaults to {exports_dir}/Invoice_{doc_number}.pdf.
        """
        if not output_path:
            out_dir = Path(self.settings.exports_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            output_path = out_dir / f"Invoice_{invoice.doc_number}.pdf"
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

        pdf_bytes = self.generate_pdf_bytes(invoice, payment_url=payment_url, order=order)
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)

        return output_path
