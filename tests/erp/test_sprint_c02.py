"""
Sprint C0.2 regression tests
==============================
Seller defaults from company_settings in outbound B2B and quote→invoice flows.

What is locked here:
  - Direct OutboundB2BService.create() without seller fields → filled from company_settings
  - Explicit seller override always wins over company_settings
  - quote→B2B conversion fills seller from company_settings automatically
  - quote→B2C/EU/INT conversion fills seller from company_settings automatically
  - Missing company_settings → seller fields stay empty, no exception raised
"""

import pytest
from uuid import uuid4
from datetime import date

from services.erp.request_context import ERPRequestContext

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


def make_ctx(company_id: str, role: str = "owner") -> ERPRequestContext:
    return ERPRequestContext(
        user_id="test-c02",
        company_id=company_id,
        role=role,
        grants=set(),
        denies=set(),
        request_id=str(uuid4()),
    )


@pytest.fixture
def cid():
    return f"test_c02_{uuid4().hex}"


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _setup_company(company_id: str) -> None:
    """Store real-ish company_settings for a test company_id."""
    from services.erp.company_service import get_company_service
    await get_company_service().upsert({
        "oib":     "47034854402",
        "name":    "Test Prodavatelj d.o.o.",
        "iban":    "HR1210010051863000160",
        "address": "Testna ulica 1",
        "city":    "Zagreb",
        "country": "HR",
    }, make_ctx(company_id))


async def _make_accepted_quote(company_id: str, customer_oib: str = "11111111110") -> str:
    """Create and mark_sent + accept a quote. Returns quote_id."""
    from services.erp.customer_service import CustomerService
    from services.erp.quote_service import QuoteService

    ctx = make_ctx(company_id)
    cust = await CustomerService().create_customer({
        "name": "Test Kupac", "oib": customer_oib, "party_type": "customer",
    }, ctx)
    q = await QuoteService().create_quote({
        "customer_id":   cust["_id"],
        "customer_name": "Test Kupac",
        "customer_oib":  customer_oib,
        "valid_until":   str(date.today()),
        "items": [{"name": "Usluga", "quantity": 1, "unit_price": 100.0, "vat_rate": 25}],
    }, ctx)
    await QuoteService().mark_sent(q["quote_id"], ctx)
    await QuoteService().accept_quote(q["quote_id"], ctx)
    return q["quote_id"]


# ── OutboundB2BService.create() ───────────────────────────────────────────────

class TestOutboundB2BSellerDefaults:

    @pytest.mark.asyncio
    async def test_create_without_seller_fields_uses_company_settings(self, cid):
        """When seller_name/seller_oib not given, company_settings fills them."""
        from services.erp.outbound_b2b_service import OutboundB2BService

        await _setup_company(cid)
        ctx = make_ctx(cid)

        inv = await OutboundB2BService().create({
            "customer_name": "Kupac d.o.o.",
            "customer_oib":  "22222222220",
            "issue_date":    str(date.today()),
            "items": [{"name": "X", "description": "X", "quantity": 1,
                       "unit": "kom", "unit_price": 200.0, "vat_rate": 25}],
        }, ctx)

        assert inv["seller_name"] == "Test Prodavatelj d.o.o.", (
            "seller_name must come from company_settings when not given"
        )
        assert inv["seller_oib"] == "47034854402", (
            "seller_oib must come from company_settings when not given"
        )
        assert inv["seller_iban"] == "HR1210010051863000160"
        assert inv["seller_city"] == "Zagreb"

    @pytest.mark.asyncio
    async def test_explicit_seller_override_wins(self, cid):
        """Explicit seller_name in data always beats company_settings."""
        from services.erp.outbound_b2b_service import OutboundB2BService

        await _setup_company(cid)
        ctx = make_ctx(cid)

        inv = await OutboundB2BService().create({
            "customer_name": "Kupac d.o.o.",
            "customer_oib":  "33333333330",
            "seller_name":   "Override Prodavatelj",
            "seller_oib":    "12345678903",
            "issue_date":    str(date.today()),
            "items": [{"name": "Y", "description": "Y", "quantity": 1,
                       "unit": "kom", "unit_price": 50.0, "vat_rate": 25}],
        }, ctx)

        assert inv["seller_name"] == "Override Prodavatelj", (
            "Explicit seller_name must not be overwritten by company_settings"
        )
        assert inv["seller_oib"] == "12345678903"

    @pytest.mark.asyncio
    async def test_missing_company_settings_leaves_seller_empty(self, cid):
        """When company_settings not configured, seller fields are empty — no exception."""
        from services.erp.outbound_b2b_service import OutboundB2BService

        # Intentionally do NOT call _setup_company(cid)
        ctx = make_ctx(cid)

        inv = await OutboundB2BService().create({
            "customer_name": "Kupac d.o.o.",
            "customer_oib":  "44444444440",
            "issue_date":    str(date.today()),
            "items": [{"name": "Z", "description": "Z", "quantity": 1,
                       "unit": "kom", "unit_price": 10.0, "vat_rate": 25}],
        }, ctx)

        # No crash — seller is simply empty
        assert inv["seller_name"] == ""
        assert inv["seller_oib"] == ""


# ── Quote → B2B conversion ────────────────────────────────────────────────────

class TestQuoteToB2BSellerDefaults:

    @pytest.mark.asyncio
    async def test_b2b_from_quote_fills_seller_from_company_settings(self, cid):
        """Quote→B2B conversion auto-fills seller from company_settings."""
        from services.erp.quote_service import QuoteService
        from services.erp.base_erp_service import get_firestore_db

        await _setup_company(cid)
        ctx = make_ctx(cid)
        quote_id = await _make_accepted_quote(cid, "55555555550")

        result = await QuoteService().convert_to_invoice(quote_id, "b2b", ctx)
        invoice_id = result["invoice_id"]

        snap = await get_firestore_db().collection("invoices_b2b").document(invoice_id).get()
        doc = snap.to_dict() or {}

        assert doc["seller_name"] == "Test Prodavatelj d.o.o.", (
            "B2B invoice from quote must have seller_name from company_settings"
        )
        assert doc["seller_oib"] == "47034854402"
        assert doc["seller_iban"] == "HR1210010051863000160"

    @pytest.mark.asyncio
    async def test_b2b_from_quote_override_wins(self, cid):
        """When create_outbound_b2b_from_quote is called with overrides, they take priority."""
        from services.erp.quote_service import QuoteService
        from services.erp.base_erp_service import get_firestore_db

        await _setup_company(cid)
        ctx = make_ctx(cid)
        quote_id = await _make_accepted_quote(cid, "66666666660")

        invoice = await QuoteService().create_outbound_b2b_from_quote(
            quote_id, ctx,
            overrides={
                "seller_name": "Explicit Override d.o.o.",
                "seller_oib":  "12345678903",
            }
        )
        invoice_id = invoice["invoice_id"]

        snap = await get_firestore_db().collection("invoices_b2b").document(invoice_id).get()
        doc = snap.to_dict() or {}

        assert doc["seller_name"] == "Explicit Override d.o.o."
        assert doc["seller_oib"]  == "12345678903"
        # seller_iban not in overrides → falls back to company_settings
        assert doc["seller_iban"] == "HR1210010051863000160"


# ── Quote → B2C / EU conversion ──────────────────────────────────────────────

class TestQuoteToNonB2BSellerDefaults:

    @pytest.mark.asyncio
    async def test_b2c_from_quote_fills_seller(self, cid):
        """Quote→B2C conversion writes seller fields from company_settings."""
        from services.erp.quote_service import QuoteService
        from services.erp.base_erp_service import get_firestore_db

        await _setup_company(cid)
        ctx = make_ctx(cid)
        quote_id = await _make_accepted_quote(cid, "77777777770")

        result = await QuoteService().convert_to_invoice(quote_id, "b2c", ctx)
        invoice_id = result["invoice_id"]

        snap = await get_firestore_db().collection("invoices_b2c").document(invoice_id).get()
        doc = snap.to_dict() or {}

        assert doc.get("seller_name") == "Test Prodavatelj d.o.o.", (
            "B2C invoice from quote must have seller_name from company_settings"
        )
        assert doc.get("seller_oib") == "47034854402"
        assert doc.get("seller_iban") == "HR1210010051863000160"

    @pytest.mark.asyncio
    async def test_eu_from_quote_fills_seller(self, cid):
        """Quote→EU conversion writes seller fields from company_settings."""
        from services.erp.quote_service import QuoteService
        from services.erp.base_erp_service import get_firestore_db

        await _setup_company(cid)
        ctx = make_ctx(cid)
        quote_id = await _make_accepted_quote(cid, "88888888880")

        result = await QuoteService().convert_to_invoice(quote_id, "eu", ctx)
        invoice_id = result["invoice_id"]

        snap = await get_firestore_db().collection("invoices_eu").document(invoice_id).get()
        doc = snap.to_dict() or {}

        assert doc.get("seller_name") == "Test Prodavatelj d.o.o."
        assert doc.get("seller_oib") == "47034854402"

    @pytest.mark.asyncio
    async def test_b2c_no_company_settings_leaves_seller_empty(self, cid):
        """Without company_settings, seller fields are empty — no crash."""
        from services.erp.quote_service import QuoteService
        from services.erp.base_erp_service import get_firestore_db

        # Intentionally no _setup_company()
        ctx = make_ctx(cid)
        quote_id = await _make_accepted_quote(cid, "99999999990")

        result = await QuoteService().convert_to_invoice(quote_id, "b2c", ctx)
        invoice_id = result["invoice_id"]

        snap = await get_firestore_db().collection("invoices_b2c").document(invoice_id).get()
        doc = snap.to_dict() or {}

        assert doc.get("seller_name", "") == ""
        assert doc.get("seller_oib", "") == ""
        # fiscalization_status still correct
        assert doc.get("fiscalization_status") == "pending"
