"""
UBL 2.1 Outbound Builder
=========================
Generates a valid UBL 2.1 / Peppol BIS Billing 3.0 XML document from an
outgoing B2B invoice dict produced by OutboundB2BService.

The generated XML conforms to:
  - UBL 2.1 (OASIS)
  - EN 16931-1 (European core invoice semantic data model)
  - Peppol BIS Billing 3.0
  - HR-FISK 2.0 CIUS (Croatian eRačun profile)

Entry point
-----------
    xml_str = build_ubl_b2b(invoice_doc)
    # Returns UTF-8 encoded XML string, raises ValueError on missing required fields.

The function uses xml.etree.ElementTree — no external libraries required.
All field values are XML-escaped by ElementTree automatically.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

# ---------------------------------------------------------------------------
# Namespace constants (Peppol BIS Billing 3.0 / UBL 2.1)
# ---------------------------------------------------------------------------
_NS_ROOT = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
_NS_CAC  = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
_NS_CBC  = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

# HR-FISK 2.0 CIUS — full customization chain:
#   EN 16931 core → Peppol BIS Billing 3.0 → Croatian MFin eRačun profile
# Source: tools/api_implementations/ubl_builder.py (HR_FISK_CUSTOMIZATION_ID)
_CUSTOMIZATION_ID = (
    "urn:cen.eu:en16931:2017#compliant"
    "#urn:fdc:peppol.eu:2017:poacc:billing:3.0"
    "#conformant#urn:fdc:mfin.hr:2023:einvoice:1.0"
)
_PROFILE_ID = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sub(parent: ET.Element, tag: str, text: Optional[str] = None,
         ns: str = _NS_CBC, **attrs) -> ET.Element:
    """Create a child element with optional text and attributes."""
    el = ET.SubElement(parent, f"{{{ns}}}{tag}", **attrs)
    if text is not None:
        el.text = str(text)
    return el


def _fmt(value, decimals: int = 2) -> str:
    """Format Decimal or float to fixed decimal string."""
    d = Decimal(str(value)).quantize(Decimal(10) ** -decimals, rounding=ROUND_HALF_UP)
    return str(d)


def _party_block(parent: ET.Element, name: str, oib: str,
                 address: str = "", city: str = "", country: str = "HR") -> None:
    """Build an AccountingSupplierParty or AccountingCustomerParty block."""
    party = _sub(parent, "Party", ns=_NS_CAC)
    pname = _sub(party, "PartyName", ns=_NS_CAC)
    _sub(pname, "Name", name)

    if address or city:
        postal = _sub(party, "PostalAddress", ns=_NS_CAC)
        if address:
            _sub(postal, "StreetName", address)
        if city:
            _sub(postal, "CityName", city)
        country_el = _sub(postal, "Country", ns=_NS_CAC)
        _sub(country_el, "IdentificationCode", country or "HR")

    if oib:
        tax_scheme = _sub(party, "PartyTaxScheme", ns=_NS_CAC)
        _sub(tax_scheme, "CompanyID", f"HR{oib}" if not oib.startswith("HR") else oib)
        ts = _sub(tax_scheme, "TaxScheme", ns=_NS_CAC)
        _sub(ts, "ID", "VAT")

    legal_entity = _sub(party, "PartyLegalEntity", ns=_NS_CAC)
    _sub(legal_entity, "RegistrationName", name)
    if oib:
        _sub(legal_entity, "CompanyID", oib)


# ---------------------------------------------------------------------------
# VAT category grouping
# ---------------------------------------------------------------------------

def _group_vat(items: list) -> list[dict]:
    """
    Group line items by VAT rate to build TaxTotal/TaxSubtotal blocks.

    Returns list of dicts: [{vat_rate, taxable_amount, tax_amount}]
    """
    buckets: dict[int, dict] = {}
    for item in items:
        rate = int(item.get("vat_rate", 25))
        qty  = Decimal(str(item.get("quantity", 1)))
        net  = Decimal(str(item.get("unit_price", 0)))
        line_net = qty * net
        line_vat = (line_net * Decimal(str(rate)) / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if rate not in buckets:
            buckets[rate] = {"vat_rate": rate, "taxable_amount": Decimal("0"), "tax_amount": Decimal("0")}
        buckets[rate]["taxable_amount"] += line_net
        buckets[rate]["tax_amount"]     += line_vat
    return list(buckets.values())


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_ubl_b2b(invoice: dict) -> str:
    """
    Generate UBL 2.1 XML for an outgoing B2B invoice.

    Args:
        invoice: Dict from OutboundB2BService (must include all required fields).

    Returns:
        UTF-8 XML string.

    Raises:
        ValueError: If required fields (invoice_number, issue_date, seller_oib,
                    customer_oib, items) are missing.
    """
    # --- Validate required fields ---
    required = ["invoice_number", "issue_date", "seller_name", "seller_oib",
                "customer_name", "customer_oib"]
    missing = [f for f in required if not invoice.get(f)]
    if missing:
        raise ValueError(f"UBL build failed — missing required fields: {missing}")

    items = invoice.get("items") or []

    # --- Register namespaces for clean output ---
    ET.register_namespace("",    _NS_ROOT)
    ET.register_namespace("cac", _NS_CAC)
    ET.register_namespace("cbc", _NS_CBC)

    root = ET.Element(f"{{{_NS_ROOT}}}Invoice")

    # ── Header ──────────────────────────────────────────────────────────────
    _sub(root, "UBLVersionID", "2.1")
    _sub(root, "CustomizationID", _CUSTOMIZATION_ID)
    _sub(root, "ProfileID", _PROFILE_ID)
    _sub(root, "ID", invoice["invoice_number"])
    _sub(root, "IssueDate", str(invoice["issue_date"])[:10])
    if invoice.get("due_date"):
        _sub(root, "DueDate", str(invoice["due_date"])[:10])
    _sub(root, "InvoiceTypeCode", "380")   # Commercial invoice
    _sub(root, "DocumentCurrencyCode", invoice.get("currency", "EUR"))
    if invoice.get("buyer_reference"):
        # EN 16931 BT-10 — mandatory when OrderReference absent.
        # B2G: typically the public-sector contract/procurement reference number.
        _sub(root, "BuyerReference", invoice["buyer_reference"])
    if invoice.get("notes"):
        _sub(root, "Note", invoice["notes"])

    # ── Payment means (optional) ─────────────────────────────────────────
    if invoice.get("seller_iban"):
        pm = _sub(root, "PaymentMeans", ns=_NS_CAC)
        _sub(pm, "PaymentMeansCode", "30")   # 30 = credit transfer
        if invoice.get("due_date"):
            _sub(pm, "PaymentDueDate", str(invoice["due_date"])[:10])
        pee = _sub(pm, "PayeeFinancialAccount", ns=_NS_CAC)
        _sub(pee, "ID", invoice["seller_iban"])

    # ── Supplier ────────────────────────────────────────────────────────────
    supplier_el = _sub(root, "AccountingSupplierParty", ns=_NS_CAC)
    _party_block(
        supplier_el,
        name    = invoice["seller_name"],
        oib     = invoice["seller_oib"],
        address = invoice.get("seller_address", ""),
        city    = invoice.get("seller_city", ""),
        country = invoice.get("seller_country", "HR"),
    )

    # ── Customer ────────────────────────────────────────────────────────────
    customer_el = _sub(root, "AccountingCustomerParty", ns=_NS_CAC)
    _party_block(
        customer_el,
        name    = invoice["customer_name"],
        oib     = invoice["customer_oib"],
        address = invoice.get("customer_address", ""),
        city    = invoice.get("customer_city", ""),
        country = invoice.get("customer_country", "HR"),
    )

    # ── Tax totals ──────────────────────────────────────────────────────────
    vat_groups = _group_vat(items)
    total_vat = sum(g["tax_amount"] for g in vat_groups) or Decimal(str(invoice.get("vat_amount", 0)))
    subtotal_net = sum(g["taxable_amount"] for g in vat_groups) or Decimal(str(invoice.get("subtotal_net", 0)))
    total_gross = Decimal(str(invoice.get("total_gross", float(subtotal_net) + float(total_vat))))

    tax_total = _sub(root, "TaxTotal", ns=_NS_CAC)
    _sub(tax_total, "TaxAmount", _fmt(total_vat), currencyID="EUR")

    for grp in vat_groups:
        subtotal_el = _sub(tax_total, "TaxSubtotal", ns=_NS_CAC)
        _sub(subtotal_el, "TaxableAmount", _fmt(grp["taxable_amount"]), currencyID="EUR")
        _sub(subtotal_el, "TaxAmount", _fmt(grp["tax_amount"]), currencyID="EUR")
        cat = _sub(subtotal_el, "TaxCategory", ns=_NS_CAC)
        _sub(cat, "ID", "S")   # S = Standard VAT
        _sub(cat, "Percent", str(grp["vat_rate"]))
        ts = _sub(cat, "TaxScheme", ns=_NS_CAC)
        _sub(ts, "ID", "VAT")

    # ── Legal monetary totals ────────────────────────────────────────────────
    lmt = _sub(root, "LegalMonetaryTotal", ns=_NS_CAC)
    _sub(lmt, "LineExtensionAmount", _fmt(subtotal_net), currencyID="EUR")
    _sub(lmt, "TaxExclusiveAmount",  _fmt(subtotal_net), currencyID="EUR")
    _sub(lmt, "TaxInclusiveAmount",  _fmt(total_gross),  currencyID="EUR")
    _sub(lmt, "PayableAmount",       _fmt(total_gross),  currencyID="EUR")

    # ── Invoice lines ────────────────────────────────────────────────────────
    for idx, item in enumerate(items, start=1):
        line = _sub(root, "InvoiceLine", ns=_NS_CAC)
        _sub(line, "ID", str(idx))

        qty = Decimal(str(item.get("quantity", 1)))
        unit = item.get("unit", "C62")  # C62 = unit (UN/ECE Rec 20)
        _sub(line, "InvoicedQuantity", _fmt(qty, decimals=4).rstrip("0").rstrip("."),
             unitCode=unit)

        net_unit = Decimal(str(item.get("unit_price", 0)))
        line_net  = (qty * net_unit).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        _sub(line, "LineExtensionAmount", _fmt(line_net), currencyID="EUR")

        # Item description
        item_el = _sub(line, "Item", ns=_NS_CAC)
        _sub(item_el, "Description", item.get("description", ""))
        _sub(item_el, "Name", item.get("name") or item.get("description", ""))

        vat_rate = int(item.get("vat_rate", 25))
        cls_tax = _sub(item_el, "ClassifiedTaxCategory", ns=_NS_CAC)
        _sub(cls_tax, "ID", "S")
        _sub(cls_tax, "Percent", str(vat_rate))
        ts2 = _sub(cls_tax, "TaxScheme", ns=_NS_CAC)
        _sub(ts2, "ID", "VAT")

        # Price
        price_el = _sub(line, "Price", ns=_NS_CAC)
        _sub(price_el, "PriceAmount", _fmt(net_unit), currencyID="EUR")

    # ── Serialise ────────────────────────────────────────────────────────────
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode", xml_declaration=False
    )
