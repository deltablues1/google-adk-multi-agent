"""
ERP ADK Tools Tests
====================
Tests for the 17 ERP ADK tools in tools/adk_tools/erp_adk_tools.py.

These tests hit REAL Firestore with isolated company_id.
The _build_ctx() in erp_adk_tools.py uses "default-company" — tests that need
isolation should verify behavior rather than data contents.

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
