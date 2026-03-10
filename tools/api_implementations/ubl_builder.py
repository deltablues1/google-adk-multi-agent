"""
UBL 2.1 Invoice Builder for Croatian Fiscalization (HR-FISK 2.0)

Generates UBL 2.1 XML invoices compliant with:
- OASIS UBL 2.1 standard
- EN 16931 European e-Invoice norm
- HR-FISK 2.0 Croatian extension

This is a DETERMINISTIC tool - no LLM involvement in XML generation.
"""

from typing import Optional, Dict, Any, List
from decimal import Decimal
from datetime import date, datetime
from lxml import etree
from lxml.builder import ElementMaker
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# UBL 2.1 NAMESPACES
# ============================================================================

NAMESPACES = {
    'ubl': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
    'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
    'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
    'ccts': 'urn:un:unece:uncefact:documentation:2',
    'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
    'qdt': 'urn:oasis:names:specification:ubl:schema:xsd:QualifiedDataTypes-2',
    'udt': 'urn:un:unece:uncefact:data:specification:UnqualifiedDataTypesSchemaModule:2',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
}

# HR-FISK 2.0 Customization ID
HR_FISK_CUSTOMIZATION_ID = "urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0#conformant#urn:fdc:mfin.hr:2023:einvoice:1.0"

# PEPPOL Profile ID
PEPPOL_PROFILE_ID = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"

# Invoice Type Codes (UNCL 1001)
INVOICE_TYPE_CODES = {
    "380": "Commercial invoice",
    "381": "Credit note",
    "383": "Debit note",
    "384": "Corrected invoice",
    "386": "Prepayment invoice",
}

# Tax Category Codes (UNCL 5305)
TAX_CATEGORY_CODES = {
    "S": "Standard rate",
    "Z": "Zero rated goods",
    "E": "Exempt from tax",
    "AE": "Reverse charge",
    "K": "Intra-community supply",
    "G": "Free export item, tax not charged",
    "O": "Services outside scope of tax",
    "L": "Canary Islands general indirect tax",
    "M": "Tax for production, services and importation in Ceuta and Melilla",
}


# ============================================================================
# UBL BUILDER CLASS
# ============================================================================

class UBLInvoiceBuilder:
    """
    Builder for UBL 2.1 Invoice XML documents.

    Supports Croatian HR-FISK 2.0 extension for fiscalization.
    """

    def __init__(self):
        """Initialize the builder with namespace-aware element makers."""
        # Create namespace-aware element makers
        self.Invoice = ElementMaker(
            namespace=NAMESPACES['ubl'],
            nsmap={
                None: NAMESPACES['ubl'],  # Default namespace
                'cac': NAMESPACES['cac'],
                'cbc': NAMESPACES['cbc'],
            }
        )

        self.cac = ElementMaker(namespace=NAMESPACES['cac'])
        self.cbc = ElementMaker(namespace=NAMESPACES['cbc'])

    def build(self, invoice_data: Dict[str, Any]) -> str:
        """
        Build UBL 2.1 Invoice XML from structured data.

        Args:
            invoice_data: Dictionary containing invoice data with keys:
                - invoice_number: str
                - invoice_type: str (default "380")
                - issue_date: date or str (YYYY-MM-DD)
                - due_date: date or str (YYYY-MM-DD)
                - currency: str (default "EUR")
                - supplier: dict with name, oib, vat_number, address, city, postal_code, country_code
                - customer: dict with name, oib, vat_number, address, city, postal_code, country_code
                - items: list of dicts with description, quantity, unit_code, unit_price, vat_rate, kpd_code
                - tax_breakdown: dict with subtotals, total_net, total_tax, total_gross
                - note: optional str
                - payment_means_code: str (default "30")
                - bank_account: optional str (IBAN)

        Returns:
            XML string (UTF-8 encoded, with XML declaration)
        """
        # Create root Invoice element
        root = self._create_root()

        # Add header elements
        self._add_header(root, invoice_data)

        # Add supplier party
        self._add_supplier_party(root, invoice_data.get('supplier', {}))

        # Add customer party
        self._add_customer_party(root, invoice_data.get('customer', {}))

        # Add payment means (if provided)
        if invoice_data.get('payment_means_code') or invoice_data.get('bank_account'):
            self._add_payment_means(root, invoice_data)

        # Add tax total
        self._add_tax_total(root, invoice_data.get('tax_breakdown', {}))

        # Add legal monetary total
        self._add_monetary_total(root, invoice_data.get('tax_breakdown', {}))

        # Add invoice lines
        for idx, item in enumerate(invoice_data.get('items', []), start=1):
            self._add_invoice_line(root, item, idx)

        # Serialize to XML string
        xml_string = etree.tostring(
            root,
            pretty_print=True,
            xml_declaration=True,
            encoding='UTF-8'
        ).decode('utf-8')

        return xml_string

    def _create_root(self) -> etree._Element:
        """Create the root Invoice element with namespaces."""
        nsmap = {
            None: NAMESPACES['ubl'],
            'cac': NAMESPACES['cac'],
            'cbc': NAMESPACES['cbc'],
        }

        root = etree.Element(
            '{%s}Invoice' % NAMESPACES['ubl'],
            nsmap=nsmap
        )

        return root

    def _add_header(self, root: etree._Element, data: Dict[str, Any]) -> None:
        """Add invoice header elements."""
        cbc = NAMESPACES['cbc']

        # UBL Version
        etree.SubElement(root, '{%s}UBLVersionID' % cbc).text = "2.1"

        # Customization ID (HR-FISK 2.0)
        etree.SubElement(root, '{%s}CustomizationID' % cbc).text = HR_FISK_CUSTOMIZATION_ID

        # Profile ID (PEPPOL)
        etree.SubElement(root, '{%s}ProfileID' % cbc).text = PEPPOL_PROFILE_ID

        # Invoice Number
        etree.SubElement(root, '{%s}ID' % cbc).text = str(data.get('invoice_number', ''))

        # Issue Date
        issue_date = data.get('issue_date')
        if isinstance(issue_date, date):
            issue_date = issue_date.isoformat()
        etree.SubElement(root, '{%s}IssueDate' % cbc).text = str(issue_date)

        # Due Date
        due_date = data.get('due_date')
        if isinstance(due_date, date):
            due_date = due_date.isoformat()
        etree.SubElement(root, '{%s}DueDate' % cbc).text = str(due_date)

        # Invoice Type Code
        invoice_type = data.get('invoice_type', '380')
        etree.SubElement(root, '{%s}InvoiceTypeCode' % cbc).text = str(invoice_type)

        # Note (optional)
        note = data.get('note')
        if note:
            etree.SubElement(root, '{%s}Note' % cbc).text = str(note)

        # Document Currency Code
        currency = data.get('currency', 'EUR')
        etree.SubElement(root, '{%s}DocumentCurrencyCode' % cbc).text = str(currency)

    def _add_supplier_party(self, root: etree._Element, supplier: Dict[str, Any]) -> None:
        """Add AccountingSupplierParty element."""
        cac = NAMESPACES['cac']
        cbc = NAMESPACES['cbc']

        supplier_party = etree.SubElement(root, '{%s}AccountingSupplierParty' % cac)
        party = etree.SubElement(supplier_party, '{%s}Party' % cac)

        # Party Name
        party_name = etree.SubElement(party, '{%s}PartyName' % cac)
        etree.SubElement(party_name, '{%s}Name' % cbc).text = str(supplier.get('name', ''))

        # Postal Address
        self._add_postal_address(party, supplier)

        # Party Tax Scheme (VAT)
        if supplier.get('vat_number'):
            tax_scheme = etree.SubElement(party, '{%s}PartyTaxScheme' % cac)
            etree.SubElement(tax_scheme, '{%s}CompanyID' % cbc).text = str(supplier.get('vat_number'))
            scheme = etree.SubElement(tax_scheme, '{%s}TaxScheme' % cac)
            etree.SubElement(scheme, '{%s}ID' % cbc).text = "VAT"

        # Party Legal Entity
        legal_entity = etree.SubElement(party, '{%s}PartyLegalEntity' % cac)
        etree.SubElement(legal_entity, '{%s}RegistrationName' % cbc).text = str(supplier.get('name', ''))
        if supplier.get('oib'):
            etree.SubElement(legal_entity, '{%s}CompanyID' % cbc).text = str(supplier.get('oib'))

    def _add_customer_party(self, root: etree._Element, customer: Dict[str, Any]) -> None:
        """Add AccountingCustomerParty element."""
        cac = NAMESPACES['cac']
        cbc = NAMESPACES['cbc']

        customer_party = etree.SubElement(root, '{%s}AccountingCustomerParty' % cac)
        party = etree.SubElement(customer_party, '{%s}Party' % cac)

        # Party Name
        party_name = etree.SubElement(party, '{%s}PartyName' % cac)
        etree.SubElement(party_name, '{%s}Name' % cbc).text = str(customer.get('name', ''))

        # Postal Address
        self._add_postal_address(party, customer)

        # Party Tax Scheme (VAT) - optional for customers
        if customer.get('vat_number'):
            tax_scheme = etree.SubElement(party, '{%s}PartyTaxScheme' % cac)
            etree.SubElement(tax_scheme, '{%s}CompanyID' % cbc).text = str(customer.get('vat_number'))
            scheme = etree.SubElement(tax_scheme, '{%s}TaxScheme' % cac)
            etree.SubElement(scheme, '{%s}ID' % cbc).text = "VAT"

        # Party Legal Entity
        legal_entity = etree.SubElement(party, '{%s}PartyLegalEntity' % cac)
        etree.SubElement(legal_entity, '{%s}RegistrationName' % cbc).text = str(customer.get('name', ''))
        if customer.get('oib'):
            etree.SubElement(legal_entity, '{%s}CompanyID' % cbc).text = str(customer.get('oib'))

    def _add_postal_address(self, party: etree._Element, address_data: Dict[str, Any]) -> None:
        """Add PostalAddress element to a party."""
        cac = NAMESPACES['cac']
        cbc = NAMESPACES['cbc']

        address = etree.SubElement(party, '{%s}PostalAddress' % cac)

        if address_data.get('address'):
            etree.SubElement(address, '{%s}StreetName' % cbc).text = str(address_data.get('address'))

        if address_data.get('city'):
            etree.SubElement(address, '{%s}CityName' % cbc).text = str(address_data.get('city'))

        if address_data.get('postal_code'):
            etree.SubElement(address, '{%s}PostalZone' % cbc).text = str(address_data.get('postal_code'))

        country = etree.SubElement(address, '{%s}Country' % cac)
        country_code = address_data.get('country_code', 'HR')
        etree.SubElement(country, '{%s}IdentificationCode' % cbc).text = str(country_code)

    def _add_payment_means(self, root: etree._Element, data: Dict[str, Any]) -> None:
        """Add PaymentMeans element."""
        cac = NAMESPACES['cac']
        cbc = NAMESPACES['cbc']

        payment_means = etree.SubElement(root, '{%s}PaymentMeans' % cac)

        # Payment Means Code (30 = Credit transfer)
        code = data.get('payment_means_code', '30')
        etree.SubElement(payment_means, '{%s}PaymentMeansCode' % cbc).text = str(code)

        # Bank account (IBAN)
        if data.get('bank_account'):
            payee_account = etree.SubElement(payment_means, '{%s}PayeeFinancialAccount' % cac)
            etree.SubElement(payee_account, '{%s}ID' % cbc).text = str(data.get('bank_account'))

    def _add_tax_total(self, root: etree._Element, tax_breakdown: Dict[str, Any]) -> None:
        """Add TaxTotal element with subtotals."""
        cac = NAMESPACES['cac']
        cbc = NAMESPACES['cbc']

        tax_total = etree.SubElement(root, '{%s}TaxTotal' % cac)

        # Total Tax Amount
        total_tax = tax_breakdown.get('total_tax', '0.00')
        currency = tax_breakdown.get('currency', 'EUR')

        tax_amount_elem = etree.SubElement(tax_total, '{%s}TaxAmount' % cbc)
        tax_amount_elem.text = str(total_tax)
        tax_amount_elem.set('currencyID', currency)

        # Tax Subtotals (per rate)
        for subtotal in tax_breakdown.get('subtotals', []):
            self._add_tax_subtotal(tax_total, subtotal, currency)

    def _add_tax_subtotal(self, tax_total: etree._Element, subtotal: Dict[str, Any], currency: str) -> None:
        """Add TaxSubtotal element."""
        cac = NAMESPACES['cac']
        cbc = NAMESPACES['cbc']

        tax_subtotal = etree.SubElement(tax_total, '{%s}TaxSubtotal' % cac)

        # Taxable Amount
        taxable = etree.SubElement(tax_subtotal, '{%s}TaxableAmount' % cbc)
        taxable.text = str(subtotal.get('taxable_amount', '0.00'))
        taxable.set('currencyID', currency)

        # Tax Amount
        tax_amt = etree.SubElement(tax_subtotal, '{%s}TaxAmount' % cbc)
        tax_amt.text = str(subtotal.get('tax_amount', '0.00'))
        tax_amt.set('currencyID', currency)

        # Tax Category
        tax_category = etree.SubElement(tax_subtotal, '{%s}TaxCategory' % cac)

        # Map VAT rate to category ID
        vat_rate = str(subtotal.get('vat_rate', '25'))
        category_id = 'S' if vat_rate != '0' else 'Z'
        etree.SubElement(tax_category, '{%s}ID' % cbc).text = category_id

        # Percent
        etree.SubElement(tax_category, '{%s}Percent' % cbc).text = vat_rate

        # Tax Scheme
        scheme = etree.SubElement(tax_category, '{%s}TaxScheme' % cac)
        etree.SubElement(scheme, '{%s}ID' % cbc).text = "VAT"

    def _add_monetary_total(self, root: etree._Element, tax_breakdown: Dict[str, Any]) -> None:
        """Add LegalMonetaryTotal element."""
        cac = NAMESPACES['cac']
        cbc = NAMESPACES['cbc']

        monetary_total = etree.SubElement(root, '{%s}LegalMonetaryTotal' % cac)

        currency = tax_breakdown.get('currency', 'EUR')
        total_net = tax_breakdown.get('total_net', '0.00')
        total_tax = tax_breakdown.get('total_tax', '0.00')
        total_gross = tax_breakdown.get('total_gross', '0.00')

        # Line Extension Amount (sum of line net amounts)
        line_ext = etree.SubElement(monetary_total, '{%s}LineExtensionAmount' % cbc)
        line_ext.text = str(total_net)
        line_ext.set('currencyID', currency)

        # Tax Exclusive Amount
        tax_excl = etree.SubElement(monetary_total, '{%s}TaxExclusiveAmount' % cbc)
        tax_excl.text = str(total_net)
        tax_excl.set('currencyID', currency)

        # Tax Inclusive Amount
        tax_incl = etree.SubElement(monetary_total, '{%s}TaxInclusiveAmount' % cbc)
        tax_incl.text = str(total_gross)
        tax_incl.set('currencyID', currency)

        # Payable Amount
        payable = etree.SubElement(monetary_total, '{%s}PayableAmount' % cbc)
        payable.text = str(total_gross)
        payable.set('currencyID', currency)

    def _add_invoice_line(self, root: etree._Element, item: Dict[str, Any], line_id: int) -> None:
        """Add InvoiceLine element."""
        cac = NAMESPACES['cac']
        cbc = NAMESPACES['cbc']

        invoice_line = etree.SubElement(root, '{%s}InvoiceLine' % cac)

        # Line ID
        etree.SubElement(invoice_line, '{%s}ID' % cbc).text = str(line_id)

        # Invoiced Quantity
        quantity = item.get('quantity', '1')
        unit_code = item.get('unit_code', 'H87')
        qty_elem = etree.SubElement(invoice_line, '{%s}InvoicedQuantity' % cbc)
        qty_elem.text = str(quantity)
        qty_elem.set('unitCode', unit_code)

        # Line Extension Amount
        line_amount = item.get('line_extension_amount')
        if line_amount is None:
            # Calculate if not provided
            qty = Decimal(str(quantity))
            price = Decimal(str(item.get('unit_price', '0')))
            line_amount = (qty * price).quantize(Decimal('0.01'))

        currency = item.get('currency', 'EUR')
        line_ext = etree.SubElement(invoice_line, '{%s}LineExtensionAmount' % cbc)
        line_ext.text = str(line_amount)
        line_ext.set('currencyID', currency)

        # Item
        item_elem = etree.SubElement(invoice_line, '{%s}Item' % cac)

        # Item Description
        if item.get('description'):
            etree.SubElement(item_elem, '{%s}Description' % cbc).text = str(item.get('description'))

        # Item Name
        etree.SubElement(item_elem, '{%s}Name' % cbc).text = str(item.get('description', 'Item'))

        # Commodity Classification (KPD Code)
        if item.get('kpd_code'):
            classification = etree.SubElement(item_elem, '{%s}CommodityClassification' % cac)
            class_code = etree.SubElement(classification, '{%s}ItemClassificationCode' % cbc)
            class_code.text = str(item.get('kpd_code'))
            class_code.set('listID', 'KPD2025')

        # Classified Tax Category
        tax_category = etree.SubElement(item_elem, '{%s}ClassifiedTaxCategory' % cac)
        vat_rate = str(item.get('vat_rate', '25'))
        category_id = 'S' if vat_rate != '0' else 'Z'
        etree.SubElement(tax_category, '{%s}ID' % cbc).text = category_id
        etree.SubElement(tax_category, '{%s}Percent' % cbc).text = vat_rate
        scheme = etree.SubElement(tax_category, '{%s}TaxScheme' % cac)
        etree.SubElement(scheme, '{%s}ID' % cbc).text = "VAT"

        # Price
        price_elem = etree.SubElement(invoice_line, '{%s}Price' % cac)
        price_amount = etree.SubElement(price_elem, '{%s}PriceAmount' % cbc)
        price_amount.text = str(item.get('unit_price', '0.00'))
        price_amount.set('currencyID', currency)


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def build_ubl_invoice(invoice_data: Dict[str, Any]) -> str:
    """
    Build UBL 2.1 Invoice XML from dictionary data.

    Convenience function that creates a builder and generates XML.

    Args:
        invoice_data: Invoice data dictionary

    Returns:
        XML string
    """
    builder = UBLInvoiceBuilder()
    return builder.build(invoice_data)


def build_ubl_from_fiskalni_podaci(fiskalni_podaci) -> str:
    """
    Build UBL 2.1 Invoice XML from FiskalniPodaci Pydantic model.

    Converts the Pydantic model to dictionary format expected by builder.

    Args:
        fiskalni_podaci: FiskalniPodaci instance

    Returns:
        XML string
    """
    # Convert Pydantic model to dict
    if hasattr(fiskalni_podaci, 'model_dump'):
        data = fiskalni_podaci.model_dump()
    elif hasattr(fiskalni_podaci, 'dict'):
        data = fiskalni_podaci.dict()
    else:
        data = dict(fiskalni_podaci)

    # Convert date objects to strings
    if isinstance(data.get('issue_date'), date):
        data['issue_date'] = data['issue_date'].isoformat()
    if isinstance(data.get('due_date'), date):
        data['due_date'] = data['due_date'].isoformat()

    # Convert Decimal to string for items
    for item in data.get('items', []):
        for key in ['quantity', 'unit_price', 'line_extension_amount']:
            if key in item and isinstance(item[key], Decimal):
                item[key] = str(item[key])

    # Build XML
    builder = UBLInvoiceBuilder()
    return builder.build(data)
