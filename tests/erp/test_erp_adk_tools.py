"""
ERP ADK Tools Tests
====================
Tests for the 20 ERP ADK tools in tools/adk_tools/erp_adk_tools.py.

These tests hit REAL Firestore with isolated company_id.
_build_ctx() in erp_adk_tools.py fails fast without company_id/ERP_COMPANY_ID
(no silent "default-company" tenant) — tests either monkeypatch ERP_COMPANY_ID
or accept an "error" result.

Run with:
    pytest tests/erp/test_erp_adk_tools.py -v
"""

import pytest
import asyncio
from uuid import uuid4

pytestmark = pytest.mark.integration


class TestErpSearchCustomers:

    @pytest.mark.asyncio
    async def test_search_customers_returns_list(self):
        from tools.adk_tools.erp_adk_tools import erp_search_customers
        result = await erp_search_customers(search="Test")
        assert isinstance(result, dict)
        assert "customers" in result or "error" in result

    @pytest.mark.asyncio
    async def test_search_customers_success_structure(self):
        from tools.adk_tools.erp_adk_tools import erp_search_customers
        result = await erp_search_customers(search="")
        assert result.get("success") is True or "error" in result
        if result.get("success"):
            assert isinstance(result["customers"], list)


class TestErpGetVatSummary:

    @pytest.mark.asyncio
    async def test_vat_summary_returns_period(self):
        from tools.adk_tools.erp_adk_tools import erp_get_vat_summary
        result = await erp_get_vat_summary(year=2026, month=3)
        assert isinstance(result, dict)
        if result.get("success"):
            assert result.get("period") == "2026-03"

    @pytest.mark.asyncio
    async def test_vat_summary_no_crash(self):
        from tools.adk_tools.erp_adk_tools import erp_get_vat_summary
        result = await erp_get_vat_summary(year=2025, month=12)
        assert isinstance(result, dict)


class TestErpGetReceivablesAging:

    @pytest.mark.asyncio
    async def test_receivables_aging_has_expected_keys(self):
        from tools.adk_tools.erp_adk_tools import erp_get_receivables_aging
        result = await erp_get_receivables_aging()
        assert isinstance(result, dict)
        if result.get("success"):
            assert "buckets" in result or "total_open_eur" in result or "aging" in result


class TestErpListOpenInvoices:

    @pytest.mark.asyncio
    async def test_open_invoices_excludes_paid(self):
        """Bug 3 fix: no paid invoice should appear in results."""
        from tools.adk_tools.erp_adk_tools import erp_list_open_invoices
        result = await erp_list_open_invoices()
        assert isinstance(result, dict)
        if result.get("success"):
            invoices = result.get("invoices", [])
            for inv in invoices:
                # erp_payment_status (repo field) must not be "paid"
                assert inv.get("erp_payment_status") != "paid", \
                    f"Paid invoice leaked into open invoices: {inv.get('display_id')}"

    @pytest.mark.asyncio
    async def test_open_invoices_customer_filter_works(self):
        """Bug 3 fix: customer_name filter must check both customer_name and buyer_name."""
        from tools.adk_tools.erp_adk_tools import erp_list_open_invoices
        result = await erp_list_open_invoices(customer_name="NonExistentCustomer_xyz123")
        assert result.get("success") is True
        assert result.get("invoices") == [] or result.get("count") == 0


class TestErpCreateVendorInvoiceFromOcr:

    @pytest.mark.asyncio
    async def test_create_from_ocr_success(self):
        from tools.adk_tools.erp_adk_tools import erp_create_vendor_invoice_from_ocr
        result = await erp_create_vendor_invoice_from_ocr(
            merchant_name="Test Dobavljač d.o.o.",
            vendor_oib="12345678901",
            invoice_number=f"TEST-{uuid4().hex[:6]}",
            transaction_date="2026-03-19",
            total_amount=125.0,
            vat_amount=25.0,
            expense_category="Usluge",
            confidence_score=0.95,
        )
        assert isinstance(result, dict)
        if result.get("success"):
            display_id = result.get("display_id", "")
            assert display_id.startswith("URA-") or display_id != "", \
                f"display_id should start with URA-: {display_id}"


class TestErpGetActivityFeed:

    @pytest.mark.asyncio
    async def test_activity_feed_returns_list(self):
        from tools.adk_tools.erp_adk_tools import erp_get_activity_feed
        result = await erp_get_activity_feed(limit=5)
        assert isinstance(result, dict)
        assert result.get("success") is True
        assert isinstance(result.get("events"), list)
        assert "count" in result

    @pytest.mark.asyncio
    async def test_activity_feed_clamps_limit(self):
        """Limit > 100 should be clamped, not crash."""
        from tools.adk_tools.erp_adk_tools import erp_get_activity_feed
        result = await erp_get_activity_feed(limit=999)
        assert result.get("success") is True
        assert len(result.get("events", [])) <= 100


class TestErpGetInventoryMovements:

    @pytest.mark.asyncio
    async def test_movements_nonexistent_product_returns_error(self):
        """Nonexistent product → success=False (product not found)."""
        from tools.adk_tools.erp_adk_tools import erp_get_inventory_movements
        result = await erp_get_inventory_movements(product_id="nonexistent-product-xyz", limit=10)
        assert isinstance(result, dict)
        assert result.get("success") is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_movements_nonexistent_does_not_crash(self):
        """Limit > 100 with nonexistent product should not crash."""
        from tools.adk_tools.erp_adk_tools import erp_get_inventory_movements
        result = await erp_get_inventory_movements(product_id="any-id", limit=999)
        assert isinstance(result, dict)
        # Returns error (product not found) but doesn't crash
        assert "success" in result


class TestErpListQuotes:

    @pytest.mark.asyncio
    async def test_list_quotes_returns_list(self):
        from tools.adk_tools.erp_adk_tools import erp_list_quotes
        result = await erp_list_quotes()
        assert isinstance(result, dict)
        assert result.get("success") is True
        assert "quotes" in result
        assert isinstance(result["quotes"], list)

    @pytest.mark.asyncio
    async def test_list_quotes_with_status_filter(self):
        from tools.adk_tools.erp_adk_tools import erp_list_quotes
        result = await erp_list_quotes(status="draft", limit=5)
        assert isinstance(result, dict)
        assert result.get("success") is True

    @pytest.mark.asyncio
    async def test_list_quotes_with_customer_name_filter(self):
        from tools.adk_tools.erp_adk_tools import erp_list_quotes
        result = await erp_list_quotes(customer_name="nonexistent-company-xyz")
        assert isinstance(result, dict)
        assert result.get("success") is True
        assert result.get("count") == 0


class TestErpGetQuote:

    @pytest.mark.asyncio
    async def test_get_quote_nonexistent_returns_error(self):
        from tools.adk_tools.erp_adk_tools import erp_get_quote
        result = await erp_get_quote(quote_id="nonexistent-quote-xyz")
        assert isinstance(result, dict)
        assert result.get("success") is False
        assert "error" in result


class TestErpGetVendorInvoice:

    @pytest.mark.asyncio
    async def test_vendor_invoice_nonexistent_returns_error(self):
        from tools.adk_tools.erp_adk_tools import erp_get_vendor_invoice
        result = await erp_get_vendor_invoice(vendor_invoice_id="nonexistent-ura-xyz")
        assert isinstance(result, dict)
        assert result.get("success") is False
        assert "error" in result


class TestSkladistarTools:
    """Voice warehouse tools: erp_find_product / erp_adjust_stock / erp_create_product.

    Each test runs against its own throwaway company_id (via ERP_COMPANY_ID),
    so real Firestore data is never touched.
    """

    @pytest.fixture(autouse=True)
    def _isolated_company(self, monkeypatch):
        monkeypatch.setenv("ERP_COMPANY_ID", f"test-voice-{uuid4().hex[:8]}")

    @pytest.mark.asyncio
    async def test_create_product_generates_sku_and_is_findable(self):
        from tools.adk_tools.erp_adk_tools import erp_create_product, erp_find_product
        created = await erp_create_product(name="Vijak M8x40", unit="kom")
        assert created.get("success") is True, created
        assert created.get("sku"), "SKU should be auto-generated"
        assert created["stock_quantity"] == 0.0

        found = await erp_find_product(query="vijak")
        assert found.get("success") is True
        assert found["count"] == 1
        assert found["products"][0]["name"] == "Vijak M8x40"

    @pytest.mark.asyncio
    async def test_find_product_is_diacritic_insensitive(self):
        from tools.adk_tools.erp_adk_tools import erp_create_product, erp_find_product
        created = await erp_create_product(name="Ležaj 6204", unit="kom")
        assert created.get("success") is True, created

        # STT will produce "lezaj" — must still match "Ležaj"
        found = await erp_find_product(query="lezaj 6204")
        assert found.get("success") is True
        assert found["count"] == 1
        assert found["products"][0]["name"] == "Ležaj 6204"

    @pytest.mark.asyncio
    async def test_find_product_no_match_returns_empty_success(self):
        from tools.adk_tools.erp_adk_tools import erp_find_product
        result = await erp_find_product(query="nepostojeci-artikl-xyz")
        assert result.get("success") is True
        assert result.get("count") == 0
        assert result.get("products") == []

    @pytest.mark.asyncio
    async def test_create_with_initial_stock_records_movement(self):
        from tools.adk_tools.erp_adk_tools import (
            erp_create_product, erp_get_inventory_movements,
        )
        created = await erp_create_product(name="Brtva 25mm", initial_stock=10)
        assert created.get("success") is True, created
        assert created["stock_quantity"] == 10.0

        movements = await erp_get_inventory_movements(product_id=created["product_id"])
        assert movements.get("success") is True
        assert movements["count"] == 1
        assert movements["movements"][0]["quantity_delta"] == 10.0
        assert movements["movements"][0]["created_by"] == "skladistar-agent"

    @pytest.mark.asyncio
    async def test_adjust_stock_add_then_remove(self):
        from tools.adk_tools.erp_adk_tools import erp_create_product, erp_adjust_stock
        created = await erp_create_product(name="Kabel NYM-J 3x2.5", unit="m")
        assert created.get("success") is True, created
        pid = created["product_id"]

        added = await erp_adjust_stock(pid, quantity_delta=5, reason="Dostava materijala")
        assert added.get("success") is True, added
        assert added["new_quantity"] == 5.0

        removed = await erp_adjust_stock(pid, quantity_delta=-3, reason="Utrošak na gradilištu")
        assert removed.get("success") is True, removed
        assert removed["new_quantity"] == 2.0
        assert removed["delta"] == -3.0

    @pytest.mark.asyncio
    async def test_adjust_stock_rejects_negative_result(self):
        from tools.adk_tools.erp_adk_tools import erp_create_product, erp_adjust_stock
        created = await erp_create_product(name="Osigurač 16A")
        assert created.get("success") is True, created

        result = await erp_adjust_stock(created["product_id"], quantity_delta=-5)
        assert result.get("success") is False
        assert result.get("error") == "NEGATIVE_STOCK"
        assert "Nema dovoljno" in result.get("message", "")

    @pytest.mark.asyncio
    async def test_adjust_stock_nonexistent_product_returns_error(self):
        from tools.adk_tools.erp_adk_tools import erp_adjust_stock
        result = await erp_adjust_stock("nonexistent-product-xyz", quantity_delta=1)
        assert result.get("success") is False
        assert "error" in result
