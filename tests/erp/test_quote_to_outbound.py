"""
Quote → Outbound B2B Invoice Tests (Faza 2E)
=============================================
Tests for:
  - QuoteService.create_outbound_b2b_from_quote() mapping   [integration]
  - POST /quotes/{id}/create-invoice                         [API]
  - Idempotency (second call returns existing invoice)       [integration]
  - Status guard (non-accepted quote → 422)                  [API]
  - Full flow: create quote → accept → create-invoice →
    approve → issue → send → archive                         [integration E2E]

Firestore uses real async client.
Drive archive calls are mocked.
"""

import pytest
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import date, timedelta

from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from services.erp.errors import BusinessError
from services.erp.request_context import ERPRequestContext
from web.erp_routes import router as erp_router, get_erp_ctx

pytestmark = pytest.mark.integration

_async_mark = pytest.mark.asyncio(loop_scope="session")


# ── App / Fixtures ──────────────────────────────────────────────────────────

def build_test_app(company_id: str) -> FastAPI:
    app = FastAPI()

    @app.exception_handler(BusinessError)
    async def biz_err(request: Request, exc: BusinessError):
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message, "field": exc.field},
        )

    app.include_router(erp_router)

    def _ctx() -> ERPRequestContext:
        return ERPRequestContext(
            user_id="test-user-2e",
            company_id=company_id,
            role="owner",
            grants=["*"],
            denies=[],
            request_id=str(uuid4()),
        )

    app.dependency_overrides[get_erp_ctx] = _ctx
    return app


@pytest.fixture(scope="module")
def company_id():
    return f"test_2e_{uuid4().hex}"


@pytest.fixture(scope="module")
def app(company_id):
    return build_test_app(company_id)


# ── Helpers ──────────────────────────────────────────────────────────────────

_QUOTE_ITEMS = [
    {
        "description": "Razvoj softvera",
        "name": "Razvoj softvera",
        "quantity": 10,
        "unit": "sat",
        "unit_price": 150.0,
        "vat_rate": 25,
    },
    {
        "description": "Testiranje",
        "name": "Testiranje",
        "quantity": 5,
        "unit": "sat",
        "unit_price": 100.0,
        "vat_rate": 25,
    },
]

_SELLER = {
    "seller_name":    "Prodavač d.o.o.",
    "seller_oib":     "98765432100",
    "seller_iban":    "HR1210010051863000160",
    "seller_address": "Ilica 1",
    "seller_city":    "Zagreb",
}


def _quote_payload(**overrides) -> dict:
    base = {
        "customer_id":   f"cust_{uuid4().hex[:8]}",
        "customer_name": "Kupac d.o.o.",
        "customer_oib":  "12345678901",
        "valid_until":   str(date.today() + timedelta(days=30)),
        "items":         _QUOTE_ITEMS,
        "notes":         "Test ponuda",
    }
    base.update(overrides)
    return base


async def _create_accepted_quote(client) -> dict:
    """Create → send → accept a quote. Returns accepted quote doc."""
    r = await client.post("/api/erp/quotes", json=_quote_payload())
    assert r.status_code == 200, r.text
    quote_id = r.json()["_id"]
    await client.post(f"/api/erp/quotes/{quote_id}/send")
    r2 = await client.post(f"/api/erp/quotes/{quote_id}/accept")
    assert r2.status_code == 200
    return r2.json()


@contextmanager
def _archive_patches():
    mock_nav = MagicMock()
    mock_nav.get_folder_id = MagicMock(return_value="root-id")
    with (
        patch("tools.drive_navigator.get_drive_navigator",
              new=AsyncMock(return_value=mock_nav)),
        patch("services.erp.outbound_archive_service._get_or_create_folder",
              new=AsyncMock(return_value="folder-id")),
        patch("services.erp.outbound_archive_service._upload_bytes_to_drive",
              new=AsyncMock(return_value={"id": "fake-file-id"})),
        patch("tools.google_api_client.create_api_client_auto",
              return_value=MagicMock(credentials=MagicMock())),
    ):
        yield


# ── create_outbound_b2b_from_quote mapping ───────────────────────────────────

@_async_mark
class TestCreateInvoiceFromQuote:

    async def test_accepted_quote_creates_draft_b2b_invoice(self, app):
        """POST /quotes/{id}/create-invoice on accepted quote → 201 + draft invoice."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_SELLER,
            )
        assert r.status_code == 201, r.text
        inv = r.json()
        assert inv["document_status"] == "draft"
        assert inv["invoice_type"] == "b2b"

    async def test_invoice_customer_fields_match_quote(self, app):
        """Customer name and OIB must be copied from quote."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_SELLER,
            )
        inv = r.json()
        assert inv["customer_name"] == quote["customer_name"]
        assert inv["customer_oib"]  == quote.get("customer_oib", "12345678901")

    async def test_invoice_items_match_quote(self, app):
        """Invoice items count and totals must match quote."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_SELLER,
            )
        inv = r.json()
        assert len(inv["items"]) == len(_QUOTE_ITEMS)
        # Totals: (10*150 + 5*100) * 1.25 = (1500 + 500) * 1.25 = 2500
        assert abs(inv["total_gross"] - 2500.0) < 0.01

    async def test_invoice_has_source_quote_id(self, app):
        """Invoice must carry source_quote_id for traceability."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_SELLER,
            )
        inv = r.json()
        assert inv.get("source_quote_id") == quote["_id"], (
            "Invoice must reference the source quote"
        )

    async def test_seller_overrides_applied(self, app):
        """Seller fields from request body must appear on the invoice."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json={**_SELLER, "seller_name": "Override Firma d.o.o."},
            )
        assert r.json()["seller_name"] == "Override Firma d.o.o."

    async def test_due_date_override_applied(self, app):
        """Explicit due_date in body must override computed default."""
        target_due = str(date.today() + timedelta(days=45))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json={**_SELLER, "due_date": target_due},
            )
        assert r.json()["due_date"] == target_due

    async def test_quote_gets_linked_invoice_id(self, app):
        """After create-invoice, the quote doc must have linked_outbound_invoice_id."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_SELLER,
            )
            inv_id = r.json()["invoice_id"]
            # Fetch the quote to check the backlink
            q = await client.get(f"/api/erp/quotes/{quote['_id']}")
        assert q.json().get("linked_outbound_invoice_id") == inv_id

    async def test_idempotent_second_call_returns_200(self, app):
        """Second call to create-invoice: 201 first, 200 second, same invoice_id."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r1 = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_SELLER,
            )
            r2 = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_SELLER,
            )
        assert r1.status_code == 201, f"First call should be 201, got {r1.status_code}"
        assert r2.status_code == 200, f"Second call should be 200 (already exists), got {r2.status_code}"
        assert r1.json()["invoice_id"] == r2.json()["invoice_id"], (
            "Second call must return the same invoice, not a new one"
        )

    async def test_idempotent_via_source_quote_id_fallback(self, app):
        """
        Hardening: if linked_outbound_invoice_id is set but the fetch fails,
        the source_quote_id fallback query must find the existing invoice
        and prevent creating a duplicate.
        """
        from unittest.mock import patch, AsyncMock
        from services.erp.errors import NotFoundError as ERPNotFound

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            quote_id = quote["_id"]

            # First call — creates invoice and links it
            r1 = await client.post(
                f"/api/erp/quotes/{quote_id}/create-invoice",
                json=_SELLER,
            )
            assert r1.status_code == 201
            inv_id = r1.json()["invoice_id"]

            # Simulate: linked_id fetch raises NotFoundError (e.g. wrong company or deleted)
            # Fallback query by source_quote_id should still find the invoice.
            with patch(
                "services.erp.outbound_b2b_service.OutboundB2BService.get",
                side_effect=ERPNotFound(code="NOT_FOUND", message="simulated fetch failure"),
            ):
                r2 = await client.post(
                    f"/api/erp/quotes/{quote_id}/create-invoice",
                    json=_SELLER,
                )

        # Must get back the same invoice via fallback, NOT create a new one
        assert r2.status_code == 200, (
            f"Fallback path should return 200 (found existing), got {r2.status_code}"
        )
        assert r2.json()["invoice_id"] == inv_id, (
            "Fallback query must return existing invoice, not create a new duplicate"
        )

    async def test_fallback_query_failure_returns_error_not_duplicate(self, app):
        """
        2E.2 hardening: if Stage 2 (source_quote_id fallback) query itself fails,
        the endpoint must return an error (422 IDEMPOTENCY_CHECK_FAILED) instead of
        silently proceeding to create a potential duplicate invoice.
        """
        from unittest.mock import patch, AsyncMock
        from services.erp.errors import NotFoundError as ERPNotFound

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            quote_id = quote["_id"]

            # First call — creates invoice and links it
            r1 = await client.post(
                f"/api/erp/quotes/{quote_id}/create-invoice",
                json=_SELLER,
            )
            assert r1.status_code == 201
            inv_id = r1.json()["invoice_id"]

            # Simulate: Stage 1 linked_id fetch fails AND Stage 2 Firestore query fails.
            # Expected behaviour: return 422 (cannot verify uniqueness), NOT 201 duplicate.
            with (
                patch(
                    "services.erp.outbound_b2b_service.OutboundB2BService.get",
                    side_effect=ERPNotFound(code="NOT_FOUND", message="stage1 fail"),
                ),
                patch(
                    "services.erp.quote_service.QuoteService._get_db",
                    side_effect=Exception("Firestore unavailable"),
                ),
            ):
                r2 = await client.post(
                    f"/api/erp/quotes/{quote_id}/create-invoice",
                    json=_SELLER,
                )

        # Must get an error, not a new 201
        assert r2.status_code == 422, (
            f"Expected 422 IDEMPOTENCY_CHECK_FAILED, got {r2.status_code}: {r2.json()}"
        )
        assert r2.json()["code"] == "IDEMPOTENCY_CHECK_FAILED"

    async def test_non_accepted_quote_returns_422(self, app):
        """Draft quote → 422 QUOTE_NOT_ACCEPTED."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/api/erp/quotes", json=_quote_payload())
            quote_id = r.json()["_id"]
            r2 = await client.post(
                f"/api/erp/quotes/{quote_id}/create-invoice",
                json=_SELLER,
            )
        assert r2.status_code == 422
        assert r2.json()["code"] == "QUOTE_NOT_ACCEPTED"

    async def test_unknown_quote_returns_404(self, app):
        """Unknown quote_id → 404."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                f"/api/erp/quotes/nonexistent-{uuid4().hex}/create-invoice",
                json=_SELLER,
            )
        assert r.status_code == 404

    async def test_created_invoice_has_all_tracking_fields(self, app):
        """Invoice created via quote flow must have all 2B/2C tracking fields."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_SELLER,
            )
        inv = r.json()
        # 2B dispatch fields
        assert "send_attempts"       in inv
        assert "last_send_error"     in inv
        assert "external_status"     in inv
        # 2C archive fields
        assert "archive_status"      in inv
        assert "archive_attempts"    in inv
        # 2D capability field
        assert "delivery_capabilities" in inv
        # 2E source
        assert "source_quote_id"     in inv


# ── Full E2E: quote → outbound lifecycle ─────────────────────────────────────

@_async_mark
class TestQuoteToOutboundE2E:

    async def test_full_flow_quote_to_archived_invoice(self, app):
        """
        Full happy path:
          create quote → send → accept →
          create-invoice (draft) →
          approve → issue → send(manual) → delivered → accept →
          archive (Drive mocked)
        """
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. Create + accept quote
            quote = await _create_accepted_quote(client)
            quote_id = quote["_id"]

            # 2. Create outbound B2B invoice from quote
            r = await client.post(
                f"/api/erp/quotes/{quote_id}/create-invoice",
                json=_SELLER,
            )
            assert r.status_code == 201
            inv = r.json()
            inv_id = inv["invoice_id"]
            assert inv["document_status"] == "draft"
            assert inv["source_quote_id"] == quote_id

            # 3. Approve
            r = await client.post(f"/api/erp/outbound-b2b/{inv_id}/approve")
            assert r.json()["document_status"] == "approved"

            # 4. Issue (UBL generated)
            r = await client.post(f"/api/erp/outbound-b2b/{inv_id}/issue")
            assert r.json()["document_status"] == "issued"
            assert r.json()["ubl_xml"] is not None

            # 5. Send (manual)
            r = await client.post(
                f"/api/erp/outbound-b2b/{inv_id}/send",
                json={"delivery_method": "manual", "delivery_target": ""},
            )
            assert r.json()["document_status"] == "eracun_sent"

            # 6. Delivered
            r = await client.post(f"/api/erp/outbound-b2b/{inv_id}/delivered")
            assert r.json()["document_status"] == "delivered"

            # 7. Accept
            r = await client.post(f"/api/erp/outbound-b2b/{inv_id}/accept")
            assert r.json()["document_status"] == "accepted"

            # 8. Archive (Drive mocked)
            with _archive_patches():
                r = await client.post(f"/api/erp/outbound-b2b/{inv_id}/archive")
            assert r.status_code == 200
            final = r.json()
            assert final["archive_status"] == "archived"
            assert final["archive_ubl_file_id"] is not None
            assert final["archive_meta_file_id"] is not None
