"""
UBL 2.1 Inbound Invoice Parser
================================
Parses UBL 2.1 XML invoices (HR-FISK 2.0 CIUS / Peppol BIS Billing 3.0)
into the canonical vendor_invoice dict used by VendorInvoiceService.

Supported profiles:
  - urn:fdc:peppol.eu:2017:poacc:billing:01:1.0
  - urn:fdc:mfin.hr:2023:einvoice:1.0

Usage:
    result = parse_ubl_invoice(xml_bytes_or_str, buyer_oib="47034854402")
    # result: {"ok": True, "data": {...}} or {"ok": False, "error": "..."}
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Optional
from xml.etree import ElementTree as ET

# ---------------------------------------------------------------------------
# UBL namespace map
# ---------------------------------------------------------------------------
_NS = {
    "ubl":  "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cac":  "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc":  "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}

_PEPPOL_PROFILE = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"
_HR_FISK_CUSTOMIZATION_FRAGMENT = "urn:fdc:mfin.hr:2023:einvoice"


def _t(root: ET.Element, xpath: str) -> str:
    """Return stripped text at xpath or empty string."""
    el = root.find(xpath, _NS)
    return (el.text or "").strip() if el is not None else ""


def _decimal(root: ET.Element, xpath: str) -> Optional[Decimal]:
    """Return Decimal at xpath or None."""
    val = _t(root, xpath)
    if not val:
        return None
    try:
        return Decimal(val)
    except InvalidOperation:
        return None


def _strip_hr_vat_prefix(tax_id: str) -> str:
    """'HR47034854402' → '47034854402'"""
    return re.sub(r"^HR", "", tax_id.strip())


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_ubl_invoice(
    xml_input: str | bytes,
    buyer_oib: str = "",
) -> dict:
    """
    Parse UBL 2.1 XML into a canonical vendor_invoice dict.

    Args:
        xml_input:  Raw XML string or bytes.
        buyer_oib:  OIB of the receiving company (used to validate buyer identity).
                    If provided and the XML buyer OIB does not match, returns an error.

    Returns:
        {"ok": True,  "data": {...}}   on success
        {"ok": False, "error": "..."}  on failure
    """
    if isinstance(xml_input, str):
        xml_input = xml_input.encode("utf-8")

    try:
        root = ET.fromstring(xml_input)
    except ET.ParseError as exc:
        return {"ok": False, "error": f"XML parse error: {exc}"}

    # Strip default namespace for simpler querying
    tag = root.tag
    if "Invoice-2" not in tag:
        return {"ok": False, "error": f"Root element is not a UBL Invoice: {tag}"}

    errors: list[str] = []

    # ------------------------------------------------------------------
    # Header metadata
    # ------------------------------------------------------------------
    customization_id = _t(root, "cbc:CustomizationID")
    profile_id       = _t(root, "cbc:ProfileID")
    invoice_id       = _t(root, "cbc:ID")
    issue_date       = _t(root, "cbc:IssueDate")
    due_date         = _t(root, "cbc:DueDate")
    invoice_type     = _t(root, "cbc:InvoiceTypeCode")   # 380=invoice, 381=credit note
    note             = _t(root, "cbc:Note")
    currency         = _t(root, "cbc:DocumentCurrencyCode")

    if not invoice_id:
        errors.append("Missing cbc:ID (invoice number)")
    if not issue_date:
        errors.append("Missing cbc:IssueDate")

    # ------------------------------------------------------------------
    # Supplier (AccountingSupplierParty)
    # ------------------------------------------------------------------
    sup = root.find("cac:AccountingSupplierParty/cac:Party", _NS)
    vendor_oib = ""
    vendor_name = ""
    if sup is not None:
        # OIB via PartyIdentification
        oib_el = sup.find("cac:PartyIdentification/cbc:ID", _NS)
        if oib_el is not None:
            vendor_oib = _strip_hr_vat_prefix(oib_el.text or "")
        # OIB via PartyTaxScheme as fallback
        if not vendor_oib:
            tax_id_el = sup.find("cac:PartyTaxScheme/cbc:CompanyID", _NS)
            if tax_id_el is not None:
                vendor_oib = _strip_hr_vat_prefix(tax_id_el.text or "")
        vendor_name = (
            _t(sup, "cac:PartyName/cbc:Name")
            or _t(sup, "cac:PartyLegalEntity/cbc:RegistrationName")
        )

    if not vendor_oib:
        errors.append("Cannot determine supplier OIB")
    if not vendor_name:
        errors.append("Cannot determine supplier name")

    # ------------------------------------------------------------------
    # Buyer (AccountingCustomerParty) — validate it's us
    # ------------------------------------------------------------------
    cust = root.find("cac:AccountingCustomerParty/cac:Party", _NS)
    buyer_oib_in_doc = ""
    if cust is not None:
        oib_el = cust.find("cac:PartyIdentification/cbc:ID", _NS)
        if oib_el is not None:
            buyer_oib_in_doc = _strip_hr_vat_prefix(oib_el.text or "")
        if not buyer_oib_in_doc:
            tax_id_el = cust.find("cac:PartyTaxScheme/cbc:CompanyID", _NS)
            if tax_id_el is not None:
                buyer_oib_in_doc = _strip_hr_vat_prefix(tax_id_el.text or "")

    if buyer_oib and buyer_oib_in_doc and buyer_oib_in_doc != buyer_oib:
        return {
            "ok": False,
            "error": (
                f"Buyer OIB mismatch: document says {buyer_oib_in_doc}, "
                f"expected {buyer_oib}. This invoice is not addressed to us."
            ),
        }

    # ------------------------------------------------------------------
    # Payment means
    # ------------------------------------------------------------------
    payment_account = _t(root, "cac:PaymentMeans/cac:PayeeFinancialAccount/cbc:ID")
    payment_means_code = _t(root, "cac:PaymentMeans/cbc:PaymentMeansCode")

    # ------------------------------------------------------------------
    # Monetary totals
    # ------------------------------------------------------------------
    totals = root.find("cac:LegalMonetaryTotal", _NS)
    subtotal_net = _decimal(totals, "cbc:TaxExclusiveAmount") if totals is not None else None
    total_gross  = _decimal(totals, "cbc:TaxInclusiveAmount") if totals is not None else None
    payable      = _decimal(totals, "cbc:PayableAmount") if totals is not None else None

    if total_gross is None:
        # Fallback: use PayableAmount
        total_gross = payable
    if total_gross is None or total_gross <= 0:
        errors.append("Cannot determine total_gross (TaxInclusiveAmount or PayableAmount)")

    # VAT total
    vat_amount = _decimal(root, "cac:TaxTotal/cbc:TaxAmount")

    # VAT breakdown
    vat_lines: list[dict] = []
    for sub in root.findall("cac:TaxTotal/cac:TaxSubtotal", _NS):
        vat_lines.append({
            "taxable_amount": str(_decimal(sub, "cbc:TaxableAmount") or ""),
            "tax_amount":     str(_decimal(sub, "cbc:TaxAmount") or ""),
            "vat_rate":       _t(sub, "cac:TaxCategory/cbc:Percent"),
            "tax_category":   _t(sub, "cac:TaxCategory/cbc:ID"),
        })

    # ------------------------------------------------------------------
    # Line items
    # ------------------------------------------------------------------
    items: list[dict] = []
    for line in root.findall("cac:InvoiceLine", _NS):
        line_id  = _t(line, "cbc:ID")
        quantity = _t(line, "cbc:InvoicedQuantity")
        qty_el   = line.find("cbc:InvoicedQuantity", _NS)
        unit     = qty_el.get("unitCode", "") if qty_el is not None else ""
        name     = _t(line, "cac:Item/cbc:Name")
        line_ext = _decimal(line, "cbc:LineExtensionAmount")
        unit_price = _decimal(line, "cac:Price/cbc:PriceAmount")
        vat_rate   = _t(line, "cac:Item/cac:ClassifiedTaxCategory/cbc:Percent")

        try:
            qty_dec = Decimal(quantity) if quantity else Decimal("1")
        except InvalidOperation:
            qty_dec = Decimal("1")

        unit_price_val = unit_price or (
            (line_ext / qty_dec).quantize(Decimal("0.01")) if line_ext and qty_dec else None
        )
        vat_rate_pct = Decimal(vat_rate) / 100 if vat_rate else Decimal("0")
        line_total = line_ext or Decimal("0")
        line_vat   = (line_total * vat_rate_pct).quantize(Decimal("0.01"))

        items.append({
            "line_id":     line_id,
            "description": name,
            "quantity":    float(qty_dec),
            "unit":        unit,
            "unit_price":  float(unit_price_val) if unit_price_val else None,
            "vat_rate":    float(vat_rate_pct * 100),
            "line_total":  float(line_total),
            "line_vat":    float(line_vat),
        })

    if not items:
        errors.append("No InvoiceLines found")

    if errors:
        return {"ok": False, "error": "; ".join(errors)}

    # ------------------------------------------------------------------
    # Compose canonical vendor_invoice dict
    # ------------------------------------------------------------------
    data = {
        # Source tracing
        "source_type":      "ubl_xml",
        "parsed_from_ubl":  True,
        "from_ocr":         False,
        # UBL metadata
        "ubl_customization_id": customization_id,
        "ubl_profile_id":       profile_id,
        "ubl_invoice_type":     invoice_type,
        # Invoice identity
        "vendor_invoice_no": invoice_id,
        "issue_date":        issue_date,
        "due_date":          due_date,
        "currency":          currency or "EUR",
        "notes":             note,
        # Vendor (supplier)
        "vendor_oib":  vendor_oib,
        "vendor_name": vendor_name,
        "vendor_id":   "",           # resolved later by VendorInvoiceService._try_match_vendor
        # Financials
        "subtotal_net": float(subtotal_net or (total_gross - (vat_amount or Decimal("0")))),
        "vat_amount":   float(vat_amount or Decimal("0")),
        "total_gross":  float(total_gross),
        "items":        items,
        "vat_breakdown": vat_lines,
        # Payment
        "payment_account":    payment_account,
        "payment_means_code": payment_means_code,
        # Status defaults
        "document_status":     "draft",
        "vat_deductible":      True,
    }

    return {"ok": True, "data": data}
