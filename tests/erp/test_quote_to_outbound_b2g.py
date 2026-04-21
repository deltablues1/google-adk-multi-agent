"""
Quote → Outbound B2G Invoice Tests (Sprint D1)
==============================================
Tests for:
  - create_outbound_b2g_from_quote() mapping             [integration]
  - POST /quotes/{id}/create-invoice?invoice_type=b2g    [API]
  - Idempotency                                          [integration]
  - Cross-type guard (B2B-linked quote → B2G request)    [integration]
  - convert_to_invoice("b2g") canonical delegation       [integration]
  - Draft reuse: create-invoice then convert_to_invoice  [integration]
  - Full flow: quote → B2G draft → approve → issue       [integration E2E]
  - B2B default unchanged (regression)                   [API]

Firestore uses real async client.
Drive archive calls are mocked where needed.
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
            user_id="test-d1-b2g",
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
    return f"test_d1_b2g_{uuid4().hex}"


@pytest.fixture(scope="module")
def app(company_id):
    return build_test_app(company_id)


# ── Helpers ──────────────────────────────────────────────────────────────────

_QUOTE_ITEMS = [
    {
        "description": "Javna usluga A",
        "name": "Javna usluga A",
        "quantity": 4,
        "unit": "sat",
        "unit_price": 200.0,
        "vat_rate": 25,
    },
]

_SELLER = {
    "seller_name":    "Isporučitelj d.o.o.",
    "seller_oib":     "11111111110",
    "seller_iban":    "HR1210010051863000160",
    "seller_address": "Trg bana 1",
    "seller_city":    "Zagreb",
}

_B2G_OVERRIDES = {
    **_SELLER,
    "invoice_type":       "b2g",
    "buyer_reference":    "UGOVOR-2026-001",
    "customer_peppol_id": "0190:12345678901",
}


def _quote_payload(**overrides) -> dict:
    base = {
        "customer_id":   f"cust_{uuid4().hex[:8]}",
        "customer_name": "Ministarstvo financija",
        "customer_oib":  "12345678901",
        "valid_until":   str(date.today() + timedelta(days=30)),
        "items":         _QUOTE_ITEMS,
        "notes":         "Test B2G ponuda",
    }
    base.update(overrides)
    return base


async def _create_accepted_quote(client) -> dict:
    """Create → send → accept a quote."""
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


# ── POST create-invoice with invoice_type=b2g ───────────────────────────────

@_async_mark
class TestCreateB2GInvoiceFromQuote:

    async def test_b2g_returns_201(self, app):
        """POST create-invoice with invoice_type=b2g → 201."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_B2G_OVERRIDES,
            )
        assert r.status_code == 201, r.text

    async def test_b2g_persisted_in_invoices_b2g_collection(self, app):
        """Invoice must be accessible via the B2G route, not the B2B route."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_B2G_OVERRIDES,
            )
            invoice_id = r.json()["invoice_id"]
            # Must be reachable via B2G endpoint
            r_b2g = await client.get(f"/api/erp/outbound-b2g/{invoice_id}")
            # Must NOT be reachable via B2B endpoint
            r_b2b = await client.get(f"/api/erp/outbound-b2b/{invoice_id}")
        assert r_b2g.status_code == 200, f"B2G invoice not found in invoices_b2g: {r_b2g.text}"
        assert r_b2b.status_code == 404, "B2G invoice must not appear in invoices_b2b"

    async def test_b2g_invoice_type_field(self, app):
        """Created invoice must have invoice_type='b2g'."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_B2G_OVERRIDES,
            )
        inv = r.json()
        assert inv["invoice_type"] == "b2g"

    async def test_b2g_display_id_prefix(self, app):
        """B2G invoice display_id must start with 'B2G-'."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_B2G_OVERRIDES,
            )
        inv = r.json()
        assert inv["display_id"].startswith("B2G-"), (
            f"Expected 'B2G-' prefix, got {inv['display_id']!r}"
        )

    async def test_b2g_buyer_reference_mapped(self, app):
        """buyer_reference override must be stored on the invoice."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_B2G_OVERRIDES,
            )
        inv = r.json()
        assert inv.get("buyer_reference") == "UGOVOR-2026-001"

    async def test_b2g_customer_peppol_id_mapped(self, app):
        """customer_peppol_id override must be stored on the invoice."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_B2G_OVERRIDES,
            )
        inv = r.json()
        assert inv.get("customer_peppol_id") == "0190:12345678901"

    async def test_b2g_delivery_target_prefilled_from_peppol_id(self, app):
        """delivery_target must equal customer_peppol_id when provided."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_B2G_OVERRIDES,
            )
        inv = r.json()
        assert inv.get("delivery_target") == inv.get("customer_peppol_id"), (
            "delivery_target should be pre-filled from customer_peppol_id"
        )

    async def test_b2g_source_quote_id_present(self, app):
        """Invoice must carry source_quote_id for traceability."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_B2G_OVERRIDES,
            )
        inv = r.json()
        assert inv.get("source_quote_id") == quote["_id"]

    async def test_b2g_quote_gets_linked_invoice_type(self, app):
        """After create-invoice(b2g), quote must have linked_outbound_invoice_type='b2g'."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_B2G_OVERRIDES,
            )
            inv_id = r.json()["invoice_id"]
            q = await client.get(f"/api/erp/quotes/{quote['_id']}")
        q_data = q.json()
        assert q_data.get("linked_outbound_invoice_id") == inv_id
        assert q_data.get("linked_outbound_invoice_type") == "b2g"

    async def test_b2g_idempotent_second_call_returns_200(self, app):
        """Second call: 201 first, 200 second, same invoice_id."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r1 = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_B2G_OVERRIDES,
            )
            r2 = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_B2G_OVERRIDES,
            )
        assert r1.status_code == 201
        assert r2.status_code == 200
        assert r1.json()["invoice_id"] == r2.json()["invoice_id"]

    async def test_b2g_non_accepted_quote_returns_422(self, app):
        """Draft quote → create-invoice(b2g) must return 422."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r_q = await client.post("/api/erp/quotes", json=_quote_payload())
            quote_id = r_q.json()["_id"]
            r = await client.post(
                f"/api/erp/quotes/{quote_id}/create-invoice",
                json={"invoice_type": "b2g"},
            )
        assert r.status_code == 422

    async def test_b2g_unknown_quote_returns_404(self, app):
        """Non-existent quote → 404."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                f"/api/erp/quotes/no-such-quote-id/create-invoice",
                json={"invoice_type": "b2g"},
            )
        assert r.status_code == 404


# ── Cross-type guard ─────────────────────────────────────────────────────────

@_async_mark
class TestCrossTypeGuard:

    async def test_b2b_linked_quote_rejects_b2g_request(self, app):
        """Quote already linked to a B2B invoice → B2G create-invoice must return 422 QUOTE_ALREADY_LINKED_TO_OTHER_OUTBOUND_TYPE."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            # Create B2B invoice first
            r_b2b = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_SELLER,  # default invoice_type=b2b
            )
            assert r_b2b.status_code == 201
            # Now try B2G
            r_b2g = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json={"invoice_type": "b2g"},
            )
        assert r_b2g.status_code == 422
        assert r_b2g.json().get("code") == "QUOTE_ALREADY_LINKED_TO_OTHER_OUTBOUND_TYPE"

    async def test_b2g_linked_quote_rejects_b2b_request(self, app):
        """Quote already linked to a B2G invoice → B2B create-invoice must return 422."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r_b2g = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_B2G_OVERRIDES,
            )
            assert r_b2g.status_code == 201
            r_b2b = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_SELLER,  # default b2b
            )
        assert r_b2b.status_code == 422
        assert r_b2b.json().get("code") == "QUOTE_ALREADY_LINKED_TO_OTHER_OUTBOUND_TYPE"


# ── convert_to_invoice("b2g") canonical delegation ──────────────────────────

@_async_mark
class TestConvertToInvoiceB2G:

    async def test_convert_uses_canonical_path_gives_b2g_prefix(self, app):
        """convert_to_invoice('b2g') must give display_id with 'B2G-' prefix."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r = await client.post(
                f"/api/erp/quotes/{quote['_id']}/convert",
                json={"invoice_type": "b2g"},
            )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("invoice_type") == "b2g"
        assert data.get("invoice_display_id", "").startswith("B2G-"), (
            f"Expected B2G- prefix, got: {data.get('invoice_display_id')!r}"
        )

    async def test_convert_b2g_marks_quote_as_converted(self, app):
        """After convert, quote.document_status must be 'converted'."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            await client.post(
                f"/api/erp/quotes/{quote['_id']}/convert",
                json={"invoice_type": "b2g"},
            )
            q = await client.get(f"/api/erp/quotes/{quote['_id']}")
        assert q.json()["document_status"] == "converted"
        assert q.json().get("converted_invoice_type") == "b2g"

    async def test_convert_b2g_reuses_existing_draft_from_create_invoice(self, app):
        """
        If create-invoice(b2g) was called first, convert_to_invoice('b2g') must reuse
        the existing draft — no duplicate invoice created.
        """
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            # Create draft first
            r_draft = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_B2G_OVERRIDES,
            )
            draft_invoice_id = r_draft.json()["invoice_id"]
            # Convert should reuse it
            r_conv = await client.post(
                f"/api/erp/quotes/{quote['_id']}/convert",
                json={"invoice_type": "b2g"},
            )
        assert r_conv.status_code == 200
        assert r_conv.json()["invoice_id"] == draft_invoice_id, (
            "convert_to_invoice must reuse the existing draft, not create a new invoice"
        )

    async def test_convert_b2g_no_raw_write_path(self, app):
        """
        convert_to_invoice('b2g') must go through OutboundB2GService.create(),
        not the raw write path. Verified by asserting the invoice appears in
        invoices_b2g and has canonical tracking fields.
        """
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r = await client.post(
                f"/api/erp/quotes/{quote['_id']}/convert",
                json={"invoice_type": "b2g"},
            )
            invoice_id = r.json()["invoice_id"]
            r_inv = await client.get(f"/api/erp/outbound-b2g/{invoice_id}")
        inv = r_inv.json()
        assert r_inv.status_code == 200
        assert inv["invoice_type"] == "b2g"
        assert inv["display_id"].startswith("B2G-")
        # Canonical tracking fields set by OutboundB2GService.create()
        assert "archive_status" in inv
        assert "erp_payment_status" in inv


# ── B2G lifecycle (approve → issue) ──────────────────────────────────────────

@_async_mark
class TestB2GFullFlow:

    async def test_b2g_draft_approve_issue(self, app):
        """Full flow: quote → B2G draft → approve → issue."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_B2G_OVERRIDES,
            )
            invoice_id = r.json()["invoice_id"]

            r_approve = await client.post(f"/api/erp/outbound-b2g/{invoice_id}/approve")
            assert r_approve.status_code == 200
            assert r_approve.json()["document_status"] == "approved"

            r_issue = await client.post(f"/api/erp/outbound-b2g/{invoice_id}/issue")
            assert r_issue.status_code == 200
            assert r_issue.json()["document_status"] == "issued"
            assert r_issue.json()["ubl_xml"], "UBL XML must be generated at issue"

    async def test_b2g_issued_invoice_has_buyer_reference_in_ubl(self, app):
        """buyer_reference must appear in the generated UBL XML."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_B2G_OVERRIDES,
            )
            invoice_id = r.json()["invoice_id"]
            await client.post(f"/api/erp/outbound-b2g/{invoice_id}/approve")
            r_issue = await client.post(f"/api/erp/outbound-b2g/{invoice_id}/issue")

        ubl = r_issue.json().get("ubl_xml", "")
        assert "UGOVOR-2026-001" in ubl, (
            "buyer_reference 'UGOVOR-2026-001' must appear in generated UBL XML"
        )


# ── B2B regression — default behaviour unchanged ─────────────────────────────

@_async_mark
class TestB2BDefaultUnchanged:

    async def test_no_body_still_creates_b2b(self, app):
        """POST create-invoice with no body → B2B invoice (backward compat)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r = await client.post(f"/api/erp/quotes/{quote['_id']}/create-invoice")
        assert r.status_code == 201
        inv = r.json()
        assert inv["invoice_type"] == "b2b"
        assert inv["display_id"].startswith("B2B-")

    async def test_explicit_b2b_type_creates_b2b(self, app):
        """Explicit invoice_type=b2b → B2B invoice."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            r = await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json={**_SELLER, "invoice_type": "b2b"},
            )
        assert r.status_code == 201
        assert r.json()["invoice_type"] == "b2b"

    async def test_b2b_linked_outbound_invoice_type_set(self, app):
        """After create-invoice(b2b), quote must have linked_outbound_invoice_type='b2b'."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            quote = await _create_accepted_quote(client)
            await client.post(
                f"/api/erp/quotes/{quote['_id']}/create-invoice",
                json=_SELLER,
            )
            q = await client.get(f"/api/erp/quotes/{quote['_id']}")
        assert q.json().get("linked_outbound_invoice_type") == "b2b"
