"""
UBL 2.1 Inbound Parser Unit Tests
====================================
Pure unit tests — no Firestore, no external services.
Tests the parse_ubl_invoice() function against fixtures and edge cases.
"""

import pytest
from pathlib import Path
from decimal import Decimal

from services.erp.ubl_inbound_parser import parse_ubl_invoice

# Path to fixture XML
FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
SAMPLE_B2B_XML = (FIXTURE_DIR / "sample_inbound_b2b.xml").read_bytes()

BUYER_OIB = "47034854402"


# ---------------------------------------------------------------------------
# Happy path: sample_inbound_b2b.xml (Hrvatski Telekom → Lux Tech)
# ---------------------------------------------------------------------------

class TestSampleB2BInvoice:

    def setup_method(self):
        self.result = parse_ubl_invoice(SAMPLE_B2B_XML, buyer_oib=BUYER_OIB)
        self.data = self.result["data"]

    def test_parse_succeeds(self):
        assert self.result["ok"] is True

    def test_source_type(self):
        assert self.data["source_type"] == "ubl_xml"
        assert self.data["parsed_from_ubl"] is True
        assert self.data["from_ocr"] is False

    def test_invoice_id(self):
        assert self.data["vendor_invoice_no"] == "THT-2026-005432"

    def test_issue_date(self):
        assert self.data["issue_date"] == "2026-03-28"

    def test_due_date(self):
        assert self.data["due_date"] == "2026-04-28"

    def test_currency(self):
        assert self.data["currency"] == "EUR"

    def test_vendor_oib(self):
        assert self.data["vendor_oib"] == "81793146560"

    def test_vendor_name(self):
        assert "Telekom" in self.data["vendor_name"]

    def test_total_gross(self):
        assert abs(self.data["total_gross"] - 224.97) < 0.01

    def test_vat_amount(self):
        assert abs(self.data["vat_amount"] - 44.99) < 0.01

    def test_subtotal_net(self):
        assert abs(self.data["subtotal_net"] - 179.98) < 0.01

    def test_items_count(self):
        assert len(self.data["items"]) == 3

    def test_item_names(self):
        names = [i["description"] for i in self.data["items"]]
        assert any("internet" in n.lower() for n in names)
        assert any("telefon" in n.lower() or "telefonij" in n.lower() for n in names)

    def test_item_line_totals_sum_to_net(self):
        total = sum(i["line_total"] for i in self.data["items"])
        assert abs(total - 179.98) < 0.01

    def test_vat_rate_25(self):
        for item in self.data["items"]:
            assert item["vat_rate"] == 25.0

    def test_payment_account_present(self):
        assert self.data["payment_account"] != ""

    def test_document_status_draft(self):
        assert self.data["document_status"] == "draft"

    def test_vat_deductible_default_true(self):
        assert self.data["vat_deductible"] is True

    def test_ubl_profile_peppol(self):
        assert "peppol" in self.data["ubl_profile_id"].lower()

    def test_note_present(self):
        assert self.data["notes"] != ""


# ---------------------------------------------------------------------------
# Buyer OIB validation
# ---------------------------------------------------------------------------

class TestBuyerOIBValidation:

    def test_correct_buyer_oib_passes(self):
        r = parse_ubl_invoice(SAMPLE_B2B_XML, buyer_oib=BUYER_OIB)
        assert r["ok"] is True

    def test_wrong_buyer_oib_rejected(self):
        r = parse_ubl_invoice(SAMPLE_B2B_XML, buyer_oib="99999999999")
        assert r["ok"] is False
        assert "mismatch" in r["error"].lower() or "Buyer" in r["error"]

    def test_no_buyer_oib_check_skipped(self):
        # buyer_oib="" → no validation, accepts any buyer
        r = parse_ubl_invoice(SAMPLE_B2B_XML, buyer_oib="")
        assert r["ok"] is True

    def test_accepts_bytes_input(self):
        r = parse_ubl_invoice(SAMPLE_B2B_XML, buyer_oib=BUYER_OIB)
        assert r["ok"] is True

    def test_accepts_string_input(self):
        r = parse_ubl_invoice(SAMPLE_B2B_XML.decode("utf-8"), buyer_oib=BUYER_OIB)
        assert r["ok"] is True


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:

    def test_invalid_xml(self):
        r = parse_ubl_invoice(b"this is not xml", buyer_oib="")
        assert r["ok"] is False
        assert "parse" in r["error"].lower() or "error" in r["error"].lower()

    def test_wrong_root_element(self):
        xml = b"""<?xml version="1.0"?><SomeOtherDoc><foo/></SomeOtherDoc>"""
        r = parse_ubl_invoice(xml, buyer_oib="")
        assert r["ok"] is False
        assert "Invoice" in r["error"] or "root" in r["error"].lower()

    def test_missing_invoice_id(self):
        xml = SAMPLE_B2B_XML.decode("utf-8")
        xml = xml.replace("<cbc:ID>THT-2026-005432</cbc:ID>", "")
        r = parse_ubl_invoice(xml.encode(), buyer_oib="")
        # May still parse but should fail or vendor_invoice_no will be empty
        # The parser requires invoice ID
        if not r["ok"]:
            assert "ID" in r["error"] or "invoice" in r["error"].lower()
        else:
            # If it parsed, ID must be empty (edge case—parser doesn't hard-block here)
            assert r["data"].get("vendor_invoice_no", "") == ""

    def test_missing_supplier_oib_returns_error(self):
        xml = SAMPLE_B2B_XML.decode("utf-8")
        # Remove OIB from supplier party identification and tax scheme
        xml = xml.replace(
            '<cbc:ID schemeID="HR:OIB">81793146560</cbc:ID>', ""
        ).replace(
            "<cbc:CompanyID>HR81793146560</cbc:CompanyID>", ""
        )
        r = parse_ubl_invoice(xml.encode(), buyer_oib="")
        assert r["ok"] is False
        assert "OIB" in r["error"] or "supplier" in r["error"].lower()
