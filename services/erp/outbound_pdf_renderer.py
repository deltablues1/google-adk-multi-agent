"""
Outbound B2B Invoice PDF Renderer (Faza 2C.2)
=============================================
Generates a human-readable PDF render of an outbound B2B invoice using ReportLab.

The PDF is a simplified A4 invoice layout in Croatian, suitable for archival
and as a readable counterpart to the machine-readable UBL 2.1 XML.

Public API
----------
  render_invoice_pdf(doc) → bytes   — returns raw PDF bytes

The result is stored as {display_id}_render.pdf alongside the UBL and meta files
in Invoices_Archive/OUT/b2b/YYYY/MM/.

Limitations
-----------
- No logo/letterhead (plain layout).
- Croatian text; VAT breakdown per line.
- No digital signature in the PDF (UBL XML is the authoritative signed document).
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Optional

logger = logging.getLogger(__name__)


def render_invoice_pdf(doc: dict) -> bytes:
    """
    Render an outbound B2B invoice document as an A4 PDF.

    Args:
        doc: Full Firestore invoice document dict. Must have at minimum:
             display_id, issue_date, seller_name, customer_name, items,
             subtotal_net, vat_amount, total_gross, currency.

    Returns:
        Raw PDF bytes (application/pdf).

    Raises:
        ImportError: if reportlab is not installed.
        Exception:   if rendering fails for any other reason.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT

    buf = BytesIO()
    doc_width, doc_height = A4
    margin = 20 * mm

    pdf = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
    )

    styles = getSampleStyleSheet()
    normal  = styles["Normal"]
    heading = styles["Heading1"]

    # Custom styles
    right_style = ParagraphStyle("right", parent=normal, alignment=TA_RIGHT)
    bold_style  = ParagraphStyle("bold",  parent=normal, fontName="Helvetica-Bold")
    small_style = ParagraphStyle("small", parent=normal, fontSize=8)
    title_style = ParagraphStyle(
        "title", parent=heading, fontSize=14, spaceAfter=2*mm, textColor=colors.HexColor("#1a1a2e"),
    )
    label_style = ParagraphStyle(
        "label", parent=normal, fontSize=8, textColor=colors.grey,
    )

    # ── helpers ──────────────────────────────────────────────────────────────

    def _s(val, default="—") -> str:
        return str(val) if val not in (None, "", []) else default

    def _eur(val) -> str:
        try:
            return f"{float(val):,.2f}"
        except (TypeError, ValueError):
            return "—"

    currency = doc.get("currency", "EUR")

    # ── Document content ─────────────────────────────────────────────────────

    story = []

    # Title bar
    story.append(Paragraph("eRačun / B2B Invoice", title_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a1a2e")))
    story.append(Spacer(1, 4 * mm))

    # Invoice header: two-column (seller left, invoice details right)
    seller_lines = [
        _s(doc.get("seller_name")),
        f"OIB: {_s(doc.get('seller_oib'))}",
        _s(doc.get("seller_address")),
        _s(doc.get("seller_city")),
        f"IBAN: {_s(doc.get('seller_iban'))}",
    ]
    detail_lines = [
        ["Broj računa:", _s(doc.get("display_id"))],
        ["Broj dokumenta:", _s(doc.get("invoice_number", doc.get("display_id")))],
        ["Datum izdavanja:", _s(doc.get("issue_date"))],
        ["Rok plaćanja:", _s(doc.get("due_date"))],
        ["Valuta:", currency],
    ]

    seller_paragraphs = [Paragraph(line, normal) for line in seller_lines if line != "—"]
    detail_table_data = [
        [Paragraph(k, label_style), Paragraph(v, bold_style)]
        for k, v in detail_lines
    ]

    header_table = Table(
        [[seller_paragraphs, Table(detail_table_data,
                                   colWidths=[45*mm, 50*mm],
                                   style=TableStyle([
                                       ("ALIGN",    (0, 0), (0, -1), "RIGHT"),
                                       ("ALIGN",    (1, 0), (1, -1), "LEFT"),
                                       ("FONTSIZE", (0, 0), (-1, -1), 9),
                                       ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                                   ]))]],
        colWidths=[doc_width - 2*margin - 100*mm, 100*mm],
        style=TableStyle([
            ("VALIGN",  (0, 0), (-1, -1), "TOP"),
            ("ALIGN",   (1, 0), (1, -1),  "RIGHT"),
        ]),
    )
    story.append(header_table)
    story.append(Spacer(1, 6 * mm))

    # Buyer section
    buyer_header = Table(
        [[Paragraph("Primatelj / Buyer", label_style)]],
        colWidths=[doc_width - 2*margin],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0f0f5")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING",    (0, 0), (-1, -1), 2),
            ("LEFTPADDING",   (0, 0), (-1, -1), 3),
        ]),
    )
    story.append(buyer_header)
    buyer_lines = [
        _s(doc.get("customer_name")),
        f"OIB: {_s(doc.get('customer_oib'))}",
        _s(doc.get("customer_address")),
        _s(doc.get("customer_city")),
    ]
    for line in buyer_lines:
        if line != "—":
            story.append(Paragraph(line, normal))
    story.append(Spacer(1, 6 * mm))

    # Items table
    col_widths = [
        doc_width - 2*margin - 80*mm,   # description
        20*mm,  # qty
        15*mm,  # unit
        25*mm,  # unit price
        20*mm,  # vat%
        20*mm,  # total
    ]
    item_header = [
        Paragraph("Opis", bold_style),
        Paragraph("Kol.", bold_style),
        Paragraph("Jed.", bold_style),
        Paragraph("Cijena", bold_style),
        Paragraph("PDV%", bold_style),
        Paragraph(f"Ukupno ({currency})", bold_style),
    ]
    item_rows = [item_header]

    items = doc.get("items") or []
    for item in items:
        desc    = _s(item.get("name") or item.get("description"))
        qty     = _s(item.get("quantity"))
        unit    = _s(item.get("unit", "kom"))
        price   = _eur(item.get("unit_price"))
        vat     = _s(item.get("vat_rate", "25"))
        total   = _eur(item.get("line_total_gross", item.get("line_total_net")))
        item_rows.append([
            Paragraph(desc, small_style),
            Paragraph(qty,   small_style),
            Paragraph(unit,  small_style),
            Paragraph(price, small_style),
            Paragraph(f"{vat}%", small_style),
            Paragraph(total, small_style),
        ])

    items_table = Table(
        item_rows,
        colWidths=col_widths,
        repeatRows=1,
        style=TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#f9f9fb")]),
            ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#ccccdd")),
            ("FONTSIZE",      (0, 0), (-1, -1), 8),
            ("TOPPADDING",    (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("ALIGN",         (1, 0), (-1, -1), "RIGHT"),
        ]),
    )
    story.append(items_table)
    story.append(Spacer(1, 4 * mm))

    # Totals
    totals_data = [
        ["Osnova (net):",   f"{_eur(doc.get('subtotal_net'))} {currency}"],
        ["PDV:",            f"{_eur(doc.get('vat_amount', doc.get('vat_total', 0)))} {currency}"],
        ["UKUPNO:",         f"{_eur(doc.get('total_gross'))} {currency}"],
    ]
    totals_table = Table(
        totals_data,
        colWidths=[40*mm, 40*mm],
        hAlign="RIGHT",
        style=TableStyle([
            ("ALIGN",     (0, 0), (-1, -1), "RIGHT"),
            ("FONTSIZE",  (0, 0), (-1, -1), 9),
            ("FONTNAME",  (0, 2), (-1, 2),  "Helvetica-Bold"),
            ("FONTSIZE",  (0, 2), (-1, 2),  10),
            ("LINEABOVE", (0, 2), (-1, 2),  0.5, colors.black),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]),
    )
    story.append(totals_table)
    story.append(Spacer(1, 4 * mm))

    # Notes
    notes = doc.get("notes")
    if notes:
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(f"Napomena: {notes}", small_style))
        story.append(Spacer(1, 2 * mm))

    # Footer
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    story.append(Spacer(1, 2 * mm))
    footer_text = (
        "Ovaj dokument generiran je sukladno HR-FISK 2.0 / UBL 2.1 / EN 16931 standardu "
        "i Peppol BIS Billing 3.0 profilu. "
        "Mjerodavni dokument je priloženi UBL 2.1 XML eRačun."
    )
    story.append(Paragraph(footer_text, small_style))

    # Build PDF
    pdf.build(story)
    return buf.getvalue()
