"""
Quote Service Integration Tests
================================
Integration tests for QuoteService — requires Firestore.

Each test uses a unique company_id for isolation.
Run with Firestore emulator for full isolation:
    firebase emulators:start --only firestore
    FIRESTORE_EMULATOR_HOST=localhost:8080 pytest tests/erp/test_quote_service.py
"""

import pytest
from uuid import uuid4
from datetime import date, timedelta

from services.erp.request_context import ERPRequestContext
from services.erp.errors import (
    ValidationError, NotFoundError, InvalidStateTransitionError
)


def make_ctx(company_id: str, role: str = "owner") -> ERPRequestContext:
    return ERPRequestContext(
        user_id="test-user",
        company_id=company_id,
        role=role,
        grants=set(),
        denies=set(),
        request_id=str(uuid4()),
    )


@pytest.fixture
def cid():
    return f"test_{uuid4().hex}"


def _sample_items():
    return [
        {"description": "Widget A", "quantity": 2, "unit_price": 50.0, "vat_rate": 25},
        {"description": "Widget B", "quantity": 1, "unit_price": 100.0, "vat_rate": 25},
    ]


def _sample_quote_data(cid_val):
    return {
        "customer_id": f"cust_{uuid4().hex[:8]}",
        "customer_name": "Test Kupac d.o.o.",
        "customer_oib": "12345678901",
        "valid_until": str(date.today() + timedelta(days=30)),
        "items": _sample_items(),
        "notes": "Test ponuda",
    }


pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


class TestQuoteCreateAndGet:

    @pytest.mark.asyncio
    async def test_create_quote_returns_display_id(self, cid):
        from services.erp.quote_service import QuoteService
        svc = QuoteService()
        ctx = make_ctx(cid)
        quote = await svc.create_quote(_sample_quote_data(cid), ctx)
        assert quote["display_id"].startswith("PON-")
        assert quote["document_status"] == "draft"
        assert quote["company_id"] == cid
        assert quote["total_gross"] == 250.0  # (2*50 + 1*100) * 1.25
        assert quote["subtotal_net"] == 200.0
        assert quote["vat_total"] == 50.0

    @pytest.mark.asyncio
    async def test_get_quote(self, cid):
        from services.erp.quote_service import QuoteService
        svc = QuoteService()
        ctx = make_ctx(cid)
        quote = await svc.create_quote(_sample_quote_data(cid), ctx)
        fetched = await svc.get_quote(quote["_id"], ctx)
        assert fetched["display_id"] == quote["display_id"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_raises_not_found(self, cid):
        from services.erp.quote_service import QuoteService
        svc = QuoteService()
        ctx = make_ctx(cid)
        with pytest.raises(NotFoundError):
            await svc.get_quote("nonexistent-id", ctx)


class TestQuoteValidation:

    @pytest.mark.asyncio
    async def test_create_without_customer_id_raises_422(self, cid):
        from services.erp.quote_service import QuoteService
        svc = QuoteService()
        ctx = make_ctx(cid)
        data = _sample_quote_data(cid)
        data["customer_id"] = ""
        with pytest.raises(ValidationError):
            await svc.create_quote(data, ctx)

    @pytest.mark.asyncio
    async def test_create_without_items_raises_422(self, cid):
        from services.erp.quote_service import QuoteService
        svc = QuoteService()
        ctx = make_ctx(cid)
        data = _sample_quote_data(cid)
        data["items"] = []
        with pytest.raises(ValidationError):
            await svc.create_quote(data, ctx)

    @pytest.mark.asyncio
    async def test_create_without_valid_until_raises_422(self, cid):
        from services.erp.quote_service import QuoteService
        svc = QuoteService()
        ctx = make_ctx(cid)
        data = _sample_quote_data(cid)
        data["valid_until"] = ""
        with pytest.raises(ValidationError):
            await svc.create_quote(data, ctx)


class TestQuoteUpdate:

    @pytest.mark.asyncio
    async def test_update_draft_quote(self, cid):
        from services.erp.quote_service import QuoteService
        svc = QuoteService()
        ctx = make_ctx(cid)
        quote = await svc.create_quote(_sample_quote_data(cid), ctx)
        updated = await svc.update_quote(quote["_id"], {"notes": "Updated notes"}, ctx)
        assert updated["notes"] == "Updated notes"

    @pytest.mark.asyncio
    async def test_cannot_update_sent_quote(self, cid):
        from services.erp.quote_service import QuoteService
        svc = QuoteService()
        ctx = make_ctx(cid)
        quote = await svc.create_quote(_sample_quote_data(cid), ctx)
        await svc.mark_sent(quote["_id"], ctx)
        with pytest.raises(ValidationError):
            await svc.update_quote(quote["_id"], {"notes": "Nope"}, ctx)


class TestQuoteStateTransitions:

    @pytest.mark.asyncio
    async def test_draft_to_sent(self, cid):
        from services.erp.quote_service import QuoteService
        svc = QuoteService()
        ctx = make_ctx(cid)
        quote = await svc.create_quote(_sample_quote_data(cid), ctx)
        sent = await svc.mark_sent(quote["_id"], ctx)
        assert sent["document_status"] == "sent"
        assert sent["sent_at"] != ""

    @pytest.mark.asyncio
    async def test_sent_to_accepted(self, cid):
        from services.erp.quote_service import QuoteService
        svc = QuoteService()
        ctx = make_ctx(cid)
        quote = await svc.create_quote(_sample_quote_data(cid), ctx)
        await svc.mark_sent(quote["_id"], ctx)
        accepted = await svc.accept_quote(quote["_id"], ctx)
        assert accepted["document_status"] == "accepted"
        assert accepted["accepted_at"] != ""

    @pytest.mark.asyncio
    async def test_sent_to_rejected(self, cid):
        from services.erp.quote_service import QuoteService
        svc = QuoteService()
        ctx = make_ctx(cid)
        quote = await svc.create_quote(_sample_quote_data(cid), ctx)
        await svc.mark_sent(quote["_id"], ctx)
        rejected = await svc.reject_quote(quote["_id"], ctx)
        assert rejected["document_status"] == "rejected"

    @pytest.mark.asyncio
    async def test_draft_to_expired(self, cid):
        from services.erp.quote_service import QuoteService
        svc = QuoteService()
        ctx = make_ctx(cid)
        quote = await svc.create_quote(_sample_quote_data(cid), ctx)
        expired = await svc.expire_quote(quote["_id"], ctx)
        assert expired["document_status"] == "expired"

    @pytest.mark.asyncio
    async def test_cannot_accept_draft(self, cid):
        from services.erp.quote_service import QuoteService
        svc = QuoteService()
        ctx = make_ctx(cid)
        quote = await svc.create_quote(_sample_quote_data(cid), ctx)
        with pytest.raises(InvalidStateTransitionError):
            await svc.accept_quote(quote["_id"], ctx)

    @pytest.mark.asyncio
    async def test_cannot_convert_draft(self, cid):
        from services.erp.quote_service import QuoteService
        svc = QuoteService()
        ctx = make_ctx(cid)
        quote = await svc.create_quote(_sample_quote_data(cid), ctx)
        with pytest.raises(InvalidStateTransitionError):
            await svc.convert_to_invoice(quote["_id"], "b2c", ctx)


class TestQuoteConvertToInvoice:

    @pytest.mark.asyncio
    async def test_convert_accepted_quote_to_invoice(self, cid):
        from services.erp.quote_service import QuoteService
        svc = QuoteService()
        ctx = make_ctx(cid)
        quote = await svc.create_quote(_sample_quote_data(cid), ctx)
        await svc.mark_sent(quote["_id"], ctx)
        await svc.accept_quote(quote["_id"], ctx)
        result = await svc.convert_to_invoice(quote["_id"], "b2c", ctx)
        assert result["already_converted"] is False
        assert result["invoice_id"] != ""
        assert result["invoice_type"] == "b2c"
        assert result["invoice_display_id"].startswith("RA-")

        # Verify quote is now converted
        updated_quote = await svc.get_quote(quote["_id"], ctx)
        assert updated_quote["document_status"] == "converted"
        assert updated_quote["converted_invoice_id"] == result["invoice_id"]

    @pytest.mark.asyncio
    async def test_convert_is_idempotent(self, cid):
        from services.erp.quote_service import QuoteService
        svc = QuoteService()
        ctx = make_ctx(cid)
        quote = await svc.create_quote(_sample_quote_data(cid), ctx)
        await svc.mark_sent(quote["_id"], ctx)
        await svc.accept_quote(quote["_id"], ctx)
        result1 = await svc.convert_to_invoice(quote["_id"], "b2c", ctx)
        result2 = await svc.convert_to_invoice(quote["_id"], "b2c", ctx)
        assert result2["already_converted"] is True
        assert result2["invoice_id"] == result1["invoice_id"]

    @pytest.mark.asyncio
    async def test_convert_invalid_type_raises_422(self, cid):
        from services.erp.quote_service import QuoteService
        svc = QuoteService()
        ctx = make_ctx(cid)
        quote = await svc.create_quote(_sample_quote_data(cid), ctx)
        await svc.mark_sent(quote["_id"], ctx)
        await svc.accept_quote(quote["_id"], ctx)
        with pytest.raises(ValidationError):
            await svc.convert_to_invoice(quote["_id"], "invalid_type", ctx)


class TestQuoteCancelWorkflow:

    @pytest.mark.asyncio
    async def test_cancel_draft_quote(self, cid):
        from services.erp.quote_service import QuoteService
        svc = QuoteService()
        ctx = make_ctx(cid)
        quote = await svc.create_quote(_sample_quote_data(cid), ctx)
        cancelled = await svc.cancel_quote(quote["_id"], ctx)
        assert cancelled["document_status"] == "cancelled"
        assert cancelled["cancelled_at"] != ""

    @pytest.mark.asyncio
    async def test_cancel_sent_quote(self, cid):
        from services.erp.quote_service import QuoteService
        svc = QuoteService()
        ctx = make_ctx(cid)
        quote = await svc.create_quote(_sample_quote_data(cid), ctx)
        await svc.mark_sent(quote["_id"], ctx)
        cancelled = await svc.cancel_quote(quote["_id"], ctx)
        assert cancelled["document_status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cannot_cancel_accepted_quote(self, cid):
        from services.erp.quote_service import QuoteService
        svc = QuoteService()
        ctx = make_ctx(cid)
        quote = await svc.create_quote(_sample_quote_data(cid), ctx)
        await svc.mark_sent(quote["_id"], ctx)
        await svc.accept_quote(quote["_id"], ctx)
        with pytest.raises(InvalidStateTransitionError):
            await svc.cancel_quote(quote["_id"], ctx)


class TestQuoteValidUntilValidation:

    @pytest.mark.asyncio
    async def test_valid_until_in_past_raises_422(self, cid):
        from services.erp.quote_service import QuoteService
        svc = QuoteService()
        ctx = make_ctx(cid)
        data = _sample_quote_data(cid)
        data["valid_until"] = str(date.today() - timedelta(days=1))
        with pytest.raises(ValidationError, match="prošlosti"):
            await svc.create_quote(data, ctx)

    @pytest.mark.asyncio
    async def test_valid_until_today_is_allowed(self, cid):
        from services.erp.quote_service import QuoteService
        svc = QuoteService()
        ctx = make_ctx(cid)
        data = _sample_quote_data(cid)
        data["valid_until"] = str(date.today())
        quote = await svc.create_quote(data, ctx)
        assert quote["valid_until"] == str(date.today())

    @pytest.mark.asyncio
    async def test_invalid_date_format_raises_422(self, cid):
        from services.erp.quote_service import QuoteService
        svc = QuoteService()
        ctx = make_ctx(cid)
        data = _sample_quote_data(cid)
        data["valid_until"] = "not-a-date"
        with pytest.raises(ValidationError, match="format"):
            await svc.create_quote(data, ctx)


class TestQuoteList:

    @pytest.mark.asyncio
    async def test_list_quotes_returns_list(self, cid):
        from services.erp.quote_service import QuoteService
        svc = QuoteService()
        ctx = make_ctx(cid)
        await svc.create_quote(_sample_quote_data(cid), ctx)
        quotes = await svc.list_quotes(ctx)
        assert isinstance(quotes, list)
        assert len(quotes) >= 1
        assert quotes[0]["company_id"] == cid
