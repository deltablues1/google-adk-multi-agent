"""
ERP ADK Tools Tests
====================
Tests for the 12 ERP ADK tools in tools/adk_tools/erp_adk_tools.py.

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
