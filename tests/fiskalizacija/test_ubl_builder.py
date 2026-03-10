"""
Unit Tests for UBL Invoice Builder

Tests the UBL 2.1 XML generation for Croatian fiscalization (HR-FISK 2.0).

Run with: pytest tests/fiskalizacija/test_ubl_builder.py -v
"""

import pytest
import asyncio
from datetime import date
from decimal import Decimal
from lxml import etree

# Import the modules to test
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tools.api_implementations.ubl_builder import (
    UBLInvoiceBuilder,
    build_ubl_invoice,
    NAMESPACES,
    HR_FISK_CUSTOMIZATION_ID,
    PEPPOL_PROFILE_ID,
)
from tools.adk_tools.fiskalizacija_adk_tools import (
    build_ubl_invoice as build_ubl_invoice_async,
    validate_xsd,
    canonicalize_xml,
)


# ============================================================================
# TEST FIXTURES
# ============================================================================

@pytest.fixture
def sample_invoice_data():
    """Sample invoice data for testing."""
    return {
        "invoice_number": "001/URED/1",
        "invoice_type": "380",
        "issue_date": "2026-01-15",
        "due_date": "2026-02-15",
        "currency": "EUR",
        "supplier": {
            "name": "Moja Tvrtka d.o.o.",
            "oib": "12345678903",
            "vat_number": "HR12345678903",
            "address": "Ulica 123",
            "city": "Zagreb",
            "postal_code": "10000",
            "country_code": "HR"
        },
        "customer": {
            "name": "Kupac d.o.o.",
            "oib": "98765432106",
            "vat_number": "HR98765432106",
            "address": "Druga ulica 456",
            "city": "Split",
            "postal_code": "21000",
            "country_code": "HR"
        },
        "items": [
            {
                "description": "IT konzultantske usluge",
                "quantity": "10",
                "unit_code": "HUR",
                "unit_price": "100.00",
                "vat_rate": "25",
                "kpd_code": "62.02.10",
                "line_extension_amount": "1000.00",
                "currency": "EUR"
            }
        ],
        "tax_breakdown": {
            "subtotals": [
                {
                    "vat_rate": "25",
                    "taxable_amount": "1000.00",
                    "tax_amount": "250.00"
                }
            ],
            "total_net": "1000.00",
            "total_tax": "250.00",
            "total_gross": "1250.00",
            "currency": "EUR"
        },
        "payment_means_code": "30",
        "bank_account": "HR1234567890123456789",
        "note": "Hvala na poslovanju!"
    }


@pytest.fixture
def minimal_invoice_data():
    """Minimal valid invoice data."""
    return {
        "invoice_number": "001/URED/1",
        "issue_date": "2026-01-15",
        "due_date": "2026-02-15",
        "supplier": {
            "name": "Test Supplier",
            "oib": "12345678903",
            "address": "Test Street 1",
            "city": "Zagreb",
            "postal_code": "10000",
            "country_code": "HR"
        },
        "customer": {
            "name": "Test Customer",
            "oib": "98765432106",
            "address": "Test Street 2",
            "city": "Split",
            "postal_code": "21000",
            "country_code": "HR"
        },
        "items": [
            {
                "description": "Test item",
                "quantity": "1",
                "unit_code": "H87",
                "unit_price": "100.00",
                "vat_rate": "25"
            }
        ],
        "tax_breakdown": {
            "subtotals": [],
            "total_net": "100.00",
            "total_tax": "25.00",
            "total_gross": "125.00",
            "currency": "EUR"
        }
    }


# ============================================================================
# BASIC XML GENERATION TESTS
# ============================================================================

class TestUBLBuilder:
    """Test UBL Invoice Builder class."""

    def test_builder_creates_valid_xml(self, sample_invoice_data):
        """Test that builder creates well-formed XML."""
        builder = UBLInvoiceBuilder()
        xml = builder.build(sample_invoice_data)

        assert xml is not None
        assert len(xml) > 0
        assert xml.startswith('<?xml version=')

    def test_xml_is_well_formed(self, sample_invoice_data):
        """Test that generated XML is well-formed."""
        builder = UBLInvoiceBuilder()
        xml = builder.build(sample_invoice_data)

        # Should parse without errors
        doc = etree.fromstring(xml.encode('utf-8'))
        assert doc is not None

    def test_xml_has_correct_root_element(self, sample_invoice_data):
        """Test that root element is Invoice with correct namespace."""
        builder = UBLInvoiceBuilder()
        xml = builder.build(sample_invoice_data)

        doc = etree.fromstring(xml.encode('utf-8'))
        assert doc.tag == '{%s}Invoice' % NAMESPACES['ubl']

    def test_convenience_function(self, sample_invoice_data):
        """Test the build_ubl_invoice convenience function."""
        xml = build_ubl_invoice(sample_invoice_data)

        assert xml is not None
        assert '<?xml' in xml
        assert 'Invoice' in xml


# ============================================================================
# HEADER ELEMENT TESTS
# ============================================================================

class TestUBLHeader:
    """Test UBL Invoice header elements."""

    def test_ubl_version_id(self, sample_invoice_data):
        """Test UBLVersionID element."""
        xml = build_ubl_invoice(sample_invoice_data)
        doc = etree.fromstring(xml.encode('utf-8'))

        version = doc.find('.//{%s}UBLVersionID' % NAMESPACES['cbc'])
        assert version is not None
        assert version.text == "2.1"

    def test_customization_id(self, sample_invoice_data):
        """Test CustomizationID for HR-FISK 2.0."""
        xml = build_ubl_invoice(sample_invoice_data)
        doc = etree.fromstring(xml.encode('utf-8'))

        custom_id = doc.find('.//{%s}CustomizationID' % NAMESPACES['cbc'])
        assert custom_id is not None
        assert HR_FISK_CUSTOMIZATION_ID in custom_id.text

    def test_profile_id(self, sample_invoice_data):
        """Test ProfileID for PEPPOL."""
        xml = build_ubl_invoice(sample_invoice_data)
        doc = etree.fromstring(xml.encode('utf-8'))

        profile = doc.find('.//{%s}ProfileID' % NAMESPACES['cbc'])
        assert profile is not None
        assert "peppol" in profile.text.lower()

    def test_invoice_number(self, sample_invoice_data):
        """Test invoice number (ID) element."""
        xml = build_ubl_invoice(sample_invoice_data)
        doc = etree.fromstring(xml.encode('utf-8'))

        inv_id = doc.find('.//{%s}ID' % NAMESPACES['cbc'])
        assert inv_id is not None
        assert inv_id.text == "001/URED/1"

    def test_issue_date(self, sample_invoice_data):
        """Test IssueDate element."""
        xml = build_ubl_invoice(sample_invoice_data)
        doc = etree.fromstring(xml.encode('utf-8'))

        issue_date = doc.find('.//{%s}IssueDate' % NAMESPACES['cbc'])
        assert issue_date is not None
        assert issue_date.text == "2026-01-15"

    def test_due_date(self, sample_invoice_data):
        """Test DueDate element."""
        xml = build_ubl_invoice(sample_invoice_data)
        doc = etree.fromstring(xml.encode('utf-8'))

        due_date = doc.find('.//{%s}DueDate' % NAMESPACES['cbc'])
        assert due_date is not None
        assert due_date.text == "2026-02-15"

    def test_invoice_type_code(self, sample_invoice_data):
        """Test InvoiceTypeCode element."""
        xml = build_ubl_invoice(sample_invoice_data)
        doc = etree.fromstring(xml.encode('utf-8'))

        type_code = doc.find('.//{%s}InvoiceTypeCode' % NAMESPACES['cbc'])
        assert type_code is not None
        assert type_code.text == "380"

    def test_currency_code(self, sample_invoice_data):
        """Test DocumentCurrencyCode element."""
        xml = build_ubl_invoice(sample_invoice_data)
        doc = etree.fromstring(xml.encode('utf-8'))

        currency = doc.find('.//{%s}DocumentCurrencyCode' % NAMESPACES['cbc'])
        assert currency is not None
        assert currency.text == "EUR"

    def test_note_element(self, sample_invoice_data):
        """Test Note element when provided."""
        xml = build_ubl_invoice(sample_invoice_data)
        doc = etree.fromstring(xml.encode('utf-8'))

        note = doc.find('.//{%s}Note' % NAMESPACES['cbc'])
        assert note is not None
        assert note.text == "Hvala na poslovanju!"


# ============================================================================
# PARTY ELEMENT TESTS
# ============================================================================

class TestUBLParties:
    """Test supplier and customer party elements."""

    def test_supplier_party_exists(self, sample_invoice_data):
        """Test AccountingSupplierParty element exists."""
        xml = build_ubl_invoice(sample_invoice_data)
        doc = etree.fromstring(xml.encode('utf-8'))

        supplier = doc.find('.//{%s}AccountingSupplierParty' % NAMESPACES['cac'])
        assert supplier is not None

    def test_supplier_name(self, sample_invoice_data):
        """Test supplier party name."""
        xml = build_ubl_invoice(sample_invoice_data)
        doc = etree.fromstring(xml.encode('utf-8'))

        # Find supplier party name
        supplier = doc.find('.//{%s}AccountingSupplierParty' % NAMESPACES['cac'])
        name = supplier.find('.//{%s}Name' % NAMESPACES['cbc'])
        assert name is not None
        assert name.text == "Moja Tvrtka d.o.o."

    def test_supplier_vat_number(self, sample_invoice_data):
        """Test supplier VAT number."""
        xml = build_ubl_invoice(sample_invoice_data)
        doc = etree.fromstring(xml.encode('utf-8'))

        supplier = doc.find('.//{%s}AccountingSupplierParty' % NAMESPACES['cac'])
        tax_scheme = supplier.find('.//{%s}PartyTaxScheme' % NAMESPACES['cac'])
        assert tax_scheme is not None

        company_id = tax_scheme.find('.//{%s}CompanyID' % NAMESPACES['cbc'])
        assert company_id is not None
        assert company_id.text == "HR12345678903"

    def test_customer_party_exists(self, sample_invoice_data):
        """Test AccountingCustomerParty element exists."""
        xml = build_ubl_invoice(sample_invoice_data)
        doc = etree.fromstring(xml.encode('utf-8'))

        customer = doc.find('.//{%s}AccountingCustomerParty' % NAMESPACES['cac'])
        assert customer is not None

    def test_customer_address(self, sample_invoice_data):
        """Test customer postal address."""
        xml = build_ubl_invoice(sample_invoice_data)
        doc = etree.fromstring(xml.encode('utf-8'))

        customer = doc.find('.//{%s}AccountingCustomerParty' % NAMESPACES['cac'])
        address = customer.find('.//{%s}PostalAddress' % NAMESPACES['cac'])
        assert address is not None

        city = address.find('.//{%s}CityName' % NAMESPACES['cbc'])
        assert city is not None
        assert city.text == "Split"


# ============================================================================
# LINE ITEM TESTS
# ============================================================================

class TestUBLLineItems:
    """Test invoice line item elements."""

    def test_invoice_line_exists(self, sample_invoice_data):
        """Test InvoiceLine element exists."""
        xml = build_ubl_invoice(sample_invoice_data)
        doc = etree.fromstring(xml.encode('utf-8'))

        lines = doc.findall('.//{%s}InvoiceLine' % NAMESPACES['cac'])
        assert len(lines) == 1

    def test_line_quantity(self, sample_invoice_data):
        """Test line item quantity."""
        xml = build_ubl_invoice(sample_invoice_data)
        doc = etree.fromstring(xml.encode('utf-8'))

        qty = doc.find('.//{%s}InvoicedQuantity' % NAMESPACES['cbc'])
        assert qty is not None
        assert qty.text == "10"
        assert qty.get('unitCode') == "HUR"

    def test_line_amount(self, sample_invoice_data):
        """Test line extension amount."""
        xml = build_ubl_invoice(sample_invoice_data)
        doc = etree.fromstring(xml.encode('utf-8'))

        line = doc.find('.//{%s}InvoiceLine' % NAMESPACES['cac'])
        amount = line.find('.//{%s}LineExtensionAmount' % NAMESPACES['cbc'])
        assert amount is not None
        assert amount.text == "1000.00"
        assert amount.get('currencyID') == "EUR"

    def test_kpd_code(self, sample_invoice_data):
        """Test KPD classification code."""
        xml = build_ubl_invoice(sample_invoice_data)
        doc = etree.fromstring(xml.encode('utf-8'))

        class_code = doc.find('.//{%s}ItemClassificationCode' % NAMESPACES['cbc'])
        assert class_code is not None
        assert class_code.text == "62.02.10"
        assert class_code.get('listID') == "KPD2025"

    def test_tax_category(self, sample_invoice_data):
        """Test classified tax category."""
        xml = build_ubl_invoice(sample_invoice_data)
        doc = etree.fromstring(xml.encode('utf-8'))

        item = doc.find('.//{%s}Item' % NAMESPACES['cac'])
        tax_cat = item.find('.//{%s}ClassifiedTaxCategory' % NAMESPACES['cac'])
        assert tax_cat is not None

        percent = tax_cat.find('.//{%s}Percent' % NAMESPACES['cbc'])
        assert percent is not None
        assert percent.text == "25"


# ============================================================================
# TAX AND MONETARY TOTAL TESTS
# ============================================================================

class TestUBLTotals:
    """Test tax total and monetary total elements."""

    def test_tax_total_exists(self, sample_invoice_data):
        """Test TaxTotal element exists."""
        xml = build_ubl_invoice(sample_invoice_data)
        doc = etree.fromstring(xml.encode('utf-8'))

        tax_total = doc.find('.//{%s}TaxTotal' % NAMESPACES['cac'])
        assert tax_total is not None

    def test_tax_amount(self, sample_invoice_data):
        """Test total tax amount."""
        xml = build_ubl_invoice(sample_invoice_data)
        doc = etree.fromstring(xml.encode('utf-8'))

        tax_total = doc.find('.//{%s}TaxTotal' % NAMESPACES['cac'])
        tax_amount = tax_total.find('.//{%s}TaxAmount' % NAMESPACES['cbc'])
        assert tax_amount is not None
        assert tax_amount.text == "250.00"

    def test_monetary_total_exists(self, sample_invoice_data):
        """Test LegalMonetaryTotal element exists."""
        xml = build_ubl_invoice(sample_invoice_data)
        doc = etree.fromstring(xml.encode('utf-8'))

        monetary = doc.find('.//{%s}LegalMonetaryTotal' % NAMESPACES['cac'])
        assert monetary is not None

    def test_payable_amount(self, sample_invoice_data):
        """Test payable amount."""
        xml = build_ubl_invoice(sample_invoice_data)
        doc = etree.fromstring(xml.encode('utf-8'))

        payable = doc.find('.//{%s}PayableAmount' % NAMESPACES['cbc'])
        assert payable is not None
        assert payable.text == "1250.00"


# ============================================================================
# ASYNC TOOL TESTS
# ============================================================================

class TestAsyncTools:
    """Test async ADK tool wrappers."""

    @pytest.mark.asyncio
    async def test_async_build_ubl_invoice(self, sample_invoice_data):
        """Test async build_ubl_invoice tool."""
        result = await build_ubl_invoice_async(sample_invoice_data)

        assert result["success"] is True
        assert result["xml"] is not None
        assert result["error"] is None
        assert "Invoice" in result["xml"]

    @pytest.mark.asyncio
    async def test_async_validate_xsd(self, sample_invoice_data):
        """Test async validate_xsd tool."""
        # First build XML
        build_result = await build_ubl_invoice_async(sample_invoice_data)
        xml = build_result["xml"]

        # Then validate
        result = await validate_xsd(xml)

        assert "valid" in result
        assert "errors" in result
        assert "schema_version" in result

    @pytest.mark.asyncio
    async def test_async_canonicalize_xml(self, sample_invoice_data):
        """Test async canonicalize_xml tool."""
        # First build XML
        build_result = await build_ubl_invoice_async(sample_invoice_data)
        xml = build_result["xml"]

        # Then canonicalize
        result = await canonicalize_xml(xml)

        assert result["success"] is True
        assert result["canonical_xml"] is not None
        assert result["method"] == "exc-c14n"


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_minimal_invoice(self, minimal_invoice_data):
        """Test with minimal required data."""
        xml = build_ubl_invoice(minimal_invoice_data)
        assert xml is not None
        assert "Invoice" in xml

    def test_multiple_line_items(self, sample_invoice_data):
        """Test with multiple line items."""
        sample_invoice_data["items"].append({
            "description": "Dodatna usluga",
            "quantity": "5",
            "unit_code": "HUR",
            "unit_price": "50.00",
            "vat_rate": "25",
            "kpd_code": "62.01.11"
        })

        xml = build_ubl_invoice(sample_invoice_data)
        doc = etree.fromstring(xml.encode('utf-8'))

        lines = doc.findall('.//{%s}InvoiceLine' % NAMESPACES['cac'])
        assert len(lines) == 2

    def test_date_object_input(self, sample_invoice_data):
        """Test with date objects instead of strings."""
        sample_invoice_data["issue_date"] = date(2026, 1, 15)
        sample_invoice_data["due_date"] = date(2026, 2, 15)

        xml = build_ubl_invoice(sample_invoice_data)
        assert "2026-01-15" in xml

    def test_no_vat_number(self, minimal_invoice_data):
        """Test when VAT number is not provided."""
        # Minimal data doesn't have vat_number
        xml = build_ubl_invoice(minimal_invoice_data)
        assert xml is not None
        # Should still be valid XML

    @pytest.mark.asyncio
    async def test_empty_invoice_data(self):
        """Test with empty invoice data."""
        result = await build_ubl_invoice_async({})

        # Should handle gracefully
        assert "success" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
