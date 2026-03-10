"""
Povratna Naknada (Deposit Refund) Service

Handles deposit refund (povratna naknada) for packaging as per Croatian regulations.

Key points:
- Povratna naknada is 0.10 EUR per unit (from 1.1.2025)
- It's a pass-through item - collected on behalf of FZOEU (Fond za zaštitu okoliša)
- NOT subject to VAT (prolazna stavka)
- Displayed as AllowanceCharge in UBL, not as regular invoice line
- Does NOT require KPD classification

References:
- Porezna uprava: https://porezna-uprava.gov.hr/hr/povratna-naknada/7815
- FZOEU: https://www.fzoeu.hr/hr/otpadna-ambalaza-unutar-sustava-povratne-naknade/9313
"""

from decimal import Decimal
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from lxml import etree
import logging

logger = logging.getLogger(__name__)

# Current deposit amount per unit (from 1.1.2025)
DEPOSIT_AMOUNT_EUR = Decimal("0.10")

# UBL namespaces
NS = {
    'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
    'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2'
}


@dataclass
class DepositRefundItem:
    """
    Single deposit refund item (e.g., bottles, cans).

    Attributes:
        description: Item description (e.g., "Staklena boca 0.5L")
        quantity: Number of units
        unit_amount: Amount per unit (default 0.10 EUR)
    """
    description: str
    quantity: int
    unit_amount: Decimal = DEPOSIT_AMOUNT_EUR

    @property
    def total_amount(self) -> Decimal:
        """Calculate total deposit amount."""
        return self.unit_amount * self.quantity

    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "quantity": self.quantity,
            "unit_amount": str(self.unit_amount),
            "total_amount": str(self.total_amount)
        }


@dataclass
class DepositRefundSummary:
    """
    Summary of all deposit refunds on an invoice.
    """
    items: List[DepositRefundItem]

    @property
    def total_quantity(self) -> int:
        """Total number of units."""
        return sum(item.quantity for item in self.items)

    @property
    def total_amount(self) -> Decimal:
        """Total deposit amount."""
        return sum(item.total_amount for item in self.items)

    def to_dict(self) -> dict:
        return {
            "items": [item.to_dict() for item in self.items],
            "total_quantity": self.total_quantity,
            "total_amount": str(self.total_amount),
            "is_pass_through": True,
            "vat_exempt": True,
            "recipient": "FZOEU - Fond za zaštitu okoliša i energetsku učinkovitost"
        }


def create_deposit_refund(
    quantity: int,
    description: str = "Povratna naknada za ambalažu",
    unit_amount: Decimal = None
) -> DepositRefundItem:
    """
    Create a deposit refund item.

    Args:
        quantity: Number of returnable units (bottles, cans, etc.)
        description: Description of the items
        unit_amount: Amount per unit (default 0.10 EUR)

    Returns:
        DepositRefundItem
    """
    if unit_amount is None:
        unit_amount = DEPOSIT_AMOUNT_EUR

    return DepositRefundItem(
        description=description,
        quantity=quantity,
        unit_amount=unit_amount
    )


def build_allowance_charge_xml(
    deposit_summary: DepositRefundSummary,
    currency: str = "EUR"
) -> etree.Element:
    """
    Build UBL AllowanceCharge element for deposit refund.

    This creates document-level charge (not line-level) that represents
    the deposit refund as a pass-through item.

    Args:
        deposit_summary: DepositRefundSummary with all deposit items
        currency: Currency code (default EUR)

    Returns:
        lxml Element for cac:AllowanceCharge
    """
    cbc = "{%s}" % NS['cbc']
    cac = "{%s}" % NS['cac']

    # Create AllowanceCharge element
    allowance_charge = etree.Element(
        f"{cac}AllowanceCharge",
        nsmap={'cac': NS['cac'], 'cbc': NS['cbc']}
    )

    # ChargeIndicator: true = charge (not allowance/discount)
    charge_indicator = etree.SubElement(allowance_charge, f"{cbc}ChargeIndicator")
    charge_indicator.text = "true"

    # AllowanceChargeReasonCode: ZZZ = mutually agreed
    reason_code = etree.SubElement(allowance_charge, f"{cbc}AllowanceChargeReasonCode")
    reason_code.set("listID", "UNCL4465")
    reason_code.text = "ZZZ"

    # AllowanceChargeReason: Description
    reason = etree.SubElement(allowance_charge, f"{cbc}AllowanceChargeReason")
    if deposit_summary.items:
        # Combine descriptions
        descriptions = [item.description for item in deposit_summary.items]
        reason.text = f"Povratna naknada: {', '.join(descriptions)} ({deposit_summary.total_quantity} kom)"
    else:
        reason.text = f"Povratna naknada ({deposit_summary.total_quantity} kom)"

    # Amount
    amount = etree.SubElement(allowance_charge, f"{cbc}Amount")
    amount.set("currencyID", currency)
    amount.text = str(deposit_summary.total_amount.quantize(Decimal("0.01")))

    # TaxCategory: Not subject to VAT (pass-through)
    tax_category = etree.SubElement(allowance_charge, f"{cac}TaxCategory")

    tax_id = etree.SubElement(tax_category, f"{cbc}ID")
    tax_id.text = "O"  # Services outside scope of tax

    tax_percent = etree.SubElement(tax_category, f"{cbc}Percent")
    tax_percent.text = "0"

    tax_exemption_reason = etree.SubElement(tax_category, f"{cbc}TaxExemptionReason")
    tax_exemption_reason.text = "Prolazna stavka - povratna naknada za FZOEU"

    tax_scheme = etree.SubElement(tax_category, f"{cac}TaxScheme")
    tax_scheme_id = etree.SubElement(tax_scheme, f"{cbc}ID")
    tax_scheme_id.text = "VAT"

    return allowance_charge


def add_deposit_to_invoice(
    invoice_root: etree.Element,
    deposit_summary: DepositRefundSummary,
    currency: str = "EUR"
) -> etree.Element:
    """
    Add deposit refund AllowanceCharge to existing UBL invoice.

    The AllowanceCharge is inserted at document level, before InvoiceLine elements.

    Args:
        invoice_root: Root element of UBL invoice
        deposit_summary: Deposit refund summary
        currency: Currency code

    Returns:
        Modified invoice root element
    """
    # Find insertion point - before first InvoiceLine
    cac = "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}"

    invoice_lines = invoice_root.findall(f".//{cac}InvoiceLine")

    if invoice_lines:
        # Insert before first InvoiceLine
        first_line = invoice_lines[0]
        parent = first_line.getparent()
        index = list(parent).index(first_line)

        allowance_charge = build_allowance_charge_xml(deposit_summary, currency)
        parent.insert(index, allowance_charge)
    else:
        # Append to invoice
        allowance_charge = build_allowance_charge_xml(deposit_summary, currency)
        invoice_root.append(allowance_charge)

    # Update LegalMonetaryTotal if present
    _update_monetary_total(invoice_root, deposit_summary, currency)

    return invoice_root


def _update_monetary_total(
    invoice_root: etree.Element,
    deposit_summary: DepositRefundSummary,
    currency: str
):
    """Update LegalMonetaryTotal to include charge amount."""
    cbc = "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}"
    cac = "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}"

    monetary_total = invoice_root.find(f".//{cac}LegalMonetaryTotal")
    if monetary_total is None:
        return

    # Add or update ChargeTotalAmount
    charge_total = monetary_total.find(f"{cbc}ChargeTotalAmount")
    if charge_total is None:
        # Find PayableAmount to insert before
        payable = monetary_total.find(f"{cbc}PayableAmount")
        if payable is not None:
            index = list(monetary_total).index(payable)
            charge_total = etree.Element(f"{cbc}ChargeTotalAmount")
            charge_total.set("currencyID", currency)
            monetary_total.insert(index, charge_total)
        else:
            charge_total = etree.SubElement(monetary_total, f"{cbc}ChargeTotalAmount")
            charge_total.set("currencyID", currency)

    # Set or add to existing charge amount
    existing = Decimal(charge_total.text) if charge_total.text else Decimal("0")
    charge_total.text = str((existing + deposit_summary.total_amount).quantize(Decimal("0.01")))

    # Update PayableAmount
    payable = monetary_total.find(f"{cbc}PayableAmount")
    if payable is not None:
        existing_payable = Decimal(payable.text) if payable.text else Decimal("0")
        payable.text = str((existing_payable + deposit_summary.total_amount).quantize(Decimal("0.01")))


def calculate_deposit_for_invoice_lines(
    lines: List[Dict[str, Any]],
    deposit_products: Dict[str, int] = None
) -> Optional[DepositRefundSummary]:
    """
    Calculate deposit refund for invoice lines.

    This helper analyzes invoice lines and calculates deposit based on:
    1. Explicit deposit_quantity in line data
    2. Product codes that are known to have deposits
    3. Automatic detection based on product description (pivo, sok, voda, etc.)

    Args:
        lines: List of invoice line dictionaries
        deposit_products: Optional dict mapping product codes to deposit units per item

    Returns:
        DepositRefundSummary or None if no deposits
    """
    deposit_items = []

    # Keywords that indicate returnable packaging
    deposit_keywords = [
        "pivo", "beer",
        "sok", "juice",
        "voda", "water",
        "gazirano", "carbonated",
        "limenka", "can",
        "boca", "bottle",
        "staklo", "glass"
    ]

    for line in lines:
        # Check for explicit deposit quantity
        deposit_qty = line.get("deposit_quantity", 0)

        if deposit_qty > 0:
            description = line.get("description", "Povratna naknada")
            deposit_items.append(DepositRefundItem(
                description=f"Povratna naknada - {description}",
                quantity=int(deposit_qty),
                unit_amount=DEPOSIT_AMOUNT_EUR
            ))
            continue

        # Check product code mapping
        if deposit_products:
            product_code = line.get("product_code", "")
            if product_code in deposit_products:
                qty = int(line.get("quantity", 1)) * deposit_products[product_code]
                deposit_items.append(DepositRefundItem(
                    description=f"Povratna naknada - {line.get('description', '')}",
                    quantity=qty,
                    unit_amount=DEPOSIT_AMOUNT_EUR
                ))
                continue

        # Auto-detect based on description (optional - can be disabled)
        description = line.get("description", "").lower()
        if any(keyword in description for keyword in deposit_keywords):
            # Check if line has returnable packaging indicator
            if line.get("has_returnable_packaging", False):
                qty = int(line.get("quantity", 1))
                deposit_items.append(DepositRefundItem(
                    description=f"Povratna naknada - {line.get('description', '')}",
                    quantity=qty,
                    unit_amount=DEPOSIT_AMOUNT_EUR
                ))

    if deposit_items:
        return DepositRefundSummary(items=deposit_items)

    return None


# ============================================================================
# High-level API for ADK tools
# ============================================================================

def create_deposit_refund_data(
    quantity: int,
    description: str = None
) -> Dict[str, Any]:
    """
    Create deposit refund data structure for invoice.

    Args:
        quantity: Number of returnable units
        description: Optional description

    Returns:
        Dictionary with deposit data ready for invoice
    """
    item = create_deposit_refund(
        quantity=quantity,
        description=description or "Povratna naknada za ambalažu"
    )

    summary = DepositRefundSummary(items=[item])

    return {
        "deposit_refund": summary.to_dict(),
        "total_quantity": summary.total_quantity,
        "total_amount": str(summary.total_amount),
        "unit_amount": str(DEPOSIT_AMOUNT_EUR),
        "note": "Prolazna stavka - ne podliježe PDV-u, ide Fondu za zaštitu okoliša (FZOEU)"
    }


def get_current_deposit_rate() -> Dict[str, Any]:
    """
    Get current deposit rate information.

    Returns:
        Dictionary with current deposit rate info
    """
    return {
        "amount_per_unit": str(DEPOSIT_AMOUNT_EUR),
        "currency": "EUR",
        "effective_from": "2025-01-01",
        "applies_to": [
            "Plastična ambalaža za pića do 3L",
            "Staklena ambalaža za pića do 3L",
            "Metalna ambalaža za pića do 3L",
            "Višeslojna (kompozitna) ambalaža do 3L"
        ],
        "recipient": "FZOEU - Fond za zaštitu okoliša i energetsku učinkovitost",
        "vat_treatment": "Nije predmet PDV-a (prolazna stavka)"
    }
