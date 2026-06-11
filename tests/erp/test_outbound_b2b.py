"""
Outbound B2B eRačun Tests (Faza 2A)
=====================================
Tests for:
  - UBL 2.1 builder                            [unit]
  - OutboundB2BService lifecycle               [integration]
  - POST /outbound-b2b                         [API]
  - Full end-to-end: draft → issued → sent → delivered → accepted
  - State machine rejection and cancellation
  - Drive archive (mocked)

Firestore uses real client (same pattern as other ERP tests).
Drive API calls are fully mocked — no real Drive connection required.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import date

import httpx
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from services.erp.errors import BusinessError
from services.erp.request_context import ERPRequestContext
from web.erp_routes import router as erp_router, get_erp_ctx

# Only apply asyncio marker to integration test classes (async), not to sync unit tests.
# Module-level pytestmark intentionally uses only 'integration' to avoid
# "asyncio marker on sync test" PytestWarnings in TestUBLOutboundBuilder.
pytestmark = pytest.mark.integration

# Applied to all async integration test classes:
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
            user_id="test-user",
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
    return f"test_{uuid4().hex}"


@pytest.fixture(scope="module")
def app(company_id):
    return build_test_app(company_id)


# ── Helpers ─────────────────────────────────────────────────────────────────

_SAMPLE_ITEMS = [
    {
        "description": "IT konzultantske usluge",
        "name": "IT konzultantske usluge",
        "quantity": 8,
        "unit": "sat",
        "unit_price": 100.00,
        "vat_rate": 25,
    },
    {
        "description": "Projektna dokumentacija",
        "name": "Projektna dokumentacija",
        "quantity": 1,
        "unit": "kom",
        "unit_price": 500.00,
        "vat_rate": 25,
    },
]


def _b2b_payload(**overrides) -> dict:
    base = {
        "customer_name": "Primatelj d.o.o.",
        "customer_oib": "12345678901",
        "seller_name": "Isporučitelj d.o.o.",
        "seller_oib": "98765432100",
        "seller_iban": "HR1210010051863000160",
        "issue_date": str(date(2026, 4, 1)),
        "due_date": str(date(2026, 5, 1)),
        "items": _SAMPLE_ITEMS,
    }
    base.update(overrides)
    return base


async def _create_invoice(client) -> dict:
    r = await client.post("/api/erp/outbound-b2b", json=_b2b_payload())
    assert r.status_code == 200, r.text
    return r.json()


# ── Unit tests: UBL builder ─────────────────────────────────────────────────

@pytest.mark.unit
class TestUBLOutboundBuilder:  # sync — no asyncio marker

    def test_build_produces_xml(self):
        from services.erp.ubl_outbound_builder import build_ubl_b2b
        doc = {
            "invoice_number": "B2B-2026-000001",
            "issue_date": "2026-04-01",
            "due_date": "2026-05-01",
            "seller_name": "Isporučitelj d.o.o.",
            "seller_oib": "98765432100",
            "customer_name": "Primatelj d.o.o.",
            "customer_oib": "12345678901",
            "items": _SAMPLE_ITEMS,
            "currency": "EUR",
        }
        xml = build_ubl_b2b(doc)
        assert xml.startswith("<?xml version=")
        assert "Invoice" in xml
        assert "2.1" in xml
        assert "Isporučitelj" in xml
        assert "Primatelj" in xml

    def test_build_contains_peppol_customization(self):
        from services.erp.ubl_outbound_builder import build_ubl_b2b
        doc = {
            "invoice_number": "TEST-001",
            "issue_date": "2026-04-01",
            "seller_name": "A d.o.o.",
            "seller_oib": "11111111111",
            "customer_name": "B d.o.o.",
            "customer_oib": "22222222222",
            "items": _SAMPLE_ITEMS,
        }
        xml = build_ubl_b2b(doc)
        assert "peppol.eu" in xml
        assert "ProfileID" in xml
        assert "InvoiceTypeCode" in xml
        assert "380" in xml            # commercial invoice code

    def test_build_contains_vat_totals(self):
        from services.erp.ubl_outbound_builder import build_ubl_b2b
        doc = {
            "invoice_number": "TEST-002",
            "issue_date": "2026-04-01",
            "seller_name": "A d.o.o.",
            "seller_oib": "11111111111",
            "customer_name": "B d.o.o.",
            "customer_oib": "22222222222",
            "items": _SAMPLE_ITEMS,
        }
        xml = build_ubl_b2b(doc)
        assert "TaxTotal" in xml
        assert "TaxAmount" in xml
        assert "LegalMonetaryTotal" in xml
        assert "PayableAmount" in xml

    def test_build_contains_invoice_lines(self):
        from services.erp.ubl_outbound_builder import build_ubl_b2b
        doc = {
            "invoice_number": "TEST-003",
            "issue_date": "2026-04-01",
            "seller_name": "A d.o.o.",
            "seller_oib": "11111111111",
            "customer_name": "B d.o.o.",
            "customer_oib": "22222222222",
            "items": _SAMPLE_ITEMS,
        }
        xml = build_ubl_b2b(doc)
        assert "InvoiceLine" in xml
        assert "IT konzultantske" in xml
        assert "Projektna dokumentacija" in xml

    def test_build_raises_on_missing_required_fields(self):
        from services.erp.ubl_outbound_builder import build_ubl_b2b
        with pytest.raises(ValueError, match="missing required fields"):
            build_ubl_b2b({"invoice_number": "X", "issue_date": "2026-01-01"})

    def test_build_oib_prefixed_with_hr(self):
        from services.erp.ubl_outbound_builder import build_ubl_b2b
        doc = {
            "invoice_number": "TEST-OIB",
            "issue_date": "2026-04-01",
            "seller_name": "A d.o.o.",
            "seller_oib": "11111111111",
            "customer_name": "B d.o.o.",
            "customer_oib": "22222222222",
            "items": _SAMPLE_ITEMS,
        }
        xml = build_ubl_b2b(doc)
        assert "HR11111111111" in xml
        assert "HR22222222222" in xml

    def test_build_iban_in_payment_means(self):
        from services.erp.ubl_outbound_builder import build_ubl_b2b
        doc = {
            "invoice_number": "TEST-IBAN",
            "issue_date": "2026-04-01",
            "seller_name": "A d.o.o.",
            "seller_oib": "11111111111",
            "seller_iban": "HR1210010051863000160",
            "customer_name": "B d.o.o.",
            "customer_oib": "22222222222",
            "items": _SAMPLE_ITEMS,
        }
        xml = build_ubl_b2b(doc)
        assert "PaymentMeans" in xml
        assert "HR1210010051863000160" in xml


# ── Integration tests: API lifecycle ────────────────────────────────────────

@_async_mark
class TestOutboundB2BCreate:

    async def test_create_returns_draft(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_invoice(client)
        assert doc["document_status"] == "draft"
        assert doc["invoice_type"] == "b2b"
        assert doc["company_id"].startswith("test_")

    async def test_create_computes_totals(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_invoice(client)
        # 8 * 100 + 1 * 500 = 1300 net, +25% VAT = 1625 gross
        assert abs(doc["subtotal_net"] - 1300.0) < 0.01
        assert abs(doc["total_gross"] - 1625.0) < 0.01

    async def test_create_missing_customer_name_returns_422(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            payload = _b2b_payload()
            payload.pop("customer_name")
            r = await client.post("/api/erp/outbound-b2b", json=payload)
        assert r.status_code == 422

    async def test_create_missing_items_returns_422(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            payload = _b2b_payload()
            payload["items"] = []
            r = await client.post("/api/erp/outbound-b2b", json=payload)
        assert r.status_code == 422   # Pydantic min_length=1 on items

    async def test_create_sets_payment_tracking_fields(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_invoice(client)
        assert doc["erp_payment_status"] == "unpaid"
        assert doc["erp_amount_paid"] == 0.0
        assert abs(doc["erp_amount_due"] - doc["total_gross"]) < 0.01

    async def test_create_sets_archive_status(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_invoice(client)
        assert doc["archive_status"] == "not_archived"


@_async_mark
class TestOutboundB2BList:

    async def test_list_returns_array(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await _create_invoice(client)
            r = await client.get("/api/erp/outbound-b2b")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert len(r.json()) >= 1

    async def test_list_strips_ubl_xml(self, app):
        """List endpoint must not return bulky ubl_xml field."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_invoice(client)
            inv_id = doc["invoice_id"]
            # Issue so ubl_xml gets populated
            await client.post(f"/api/erp/outbound-b2b/{inv_id}/approve")
            await client.post(f"/api/erp/outbound-b2b/{inv_id}/issue")
            r = await client.get("/api/erp/outbound-b2b")
        for item in r.json():
            assert "ubl_xml" not in item


@_async_mark
class TestOutboundB2BGetSingle:

    async def test_get_returns_full_doc(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_invoice(client)
            r = await client.get(f"/api/erp/outbound-b2b/{doc['invoice_id']}")
        assert r.status_code == 200
        data = r.json()
        assert data["invoice_id"] == doc["invoice_id"]
        assert data["document_status"] == "draft"

    async def test_get_unknown_id_returns_404(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get(f"/api/erp/outbound-b2b/{uuid4()}")
        assert r.status_code == 404


@_async_mark
class TestOutboundB2BApprove:

    async def test_approve_transitions_to_approved(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_invoice(client)
            r = await client.post(f"/api/erp/outbound-b2b/{doc['invoice_id']}/approve")
        assert r.status_code == 200
        assert r.json()["document_status"] == "approved"

    async def test_approve_twice_is_invalid(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_invoice(client)
            inv_id = doc["invoice_id"]
            await client.post(f"/api/erp/outbound-b2b/{inv_id}/approve")
            r = await client.post(f"/api/erp/outbound-b2b/{inv_id}/approve")
        assert r.status_code == 409    # InvalidStateTransitionError


@_async_mark
class TestOutboundB2BIssue:

    async def test_issue_generates_ubl_xml(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_invoice(client)
            inv_id = doc["invoice_id"]
            await client.post(f"/api/erp/outbound-b2b/{inv_id}/approve")
            r = await client.post(f"/api/erp/outbound-b2b/{inv_id}/issue")
        assert r.status_code == 200
        result = r.json()
        assert result["document_status"] == "issued"
        assert result["ubl_xml"] is not None
        assert "<?xml" in result["ubl_xml"]

    async def test_issue_requires_approved_status(self, app):
        """Cannot issue a draft directly — must approve first."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_invoice(client)
            r = await client.post(f"/api/erp/outbound-b2b/{doc['invoice_id']}/issue")
        assert r.status_code == 409    # InvalidStateTransitionError: draft → issued not allowed

    async def test_issue_fails_when_seller_oib_missing(self, app):
        """UBL generation must fail gracefully if seller_oib is not set."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            payload = _b2b_payload(seller_oib="", seller_name="")
            r = await client.post("/api/erp/outbound-b2b", json=payload)
            doc = r.json()
            inv_id = doc["invoice_id"]
            await client.post(f"/api/erp/outbound-b2b/{inv_id}/approve")
            r = await client.post(f"/api/erp/outbound-b2b/{inv_id}/issue")
        # seller_oib/seller_name missing → pre-issue validation → 422
        assert r.status_code == 422
        assert r.json()["code"] == "UBL_MISSING_FIELDS"


@_async_mark
class TestOutboundB2BSend:

    async def test_send_transitions_to_eracun_sent(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_invoice(client)
            inv_id = doc["invoice_id"]
            await client.post(f"/api/erp/outbound-b2b/{inv_id}/approve")
            await client.post(f"/api/erp/outbound-b2b/{inv_id}/issue")
            r = await client.post(
                f"/api/erp/outbound-b2b/{inv_id}/send",
                json={"delivery_method": "manual", "delivery_target": "buyer@test.hr"},
            )
        assert r.status_code == 200
        result = r.json()
        assert result["document_status"] == "eracun_sent"
        assert result["delivery_method"] == "manual"
        assert result["delivery_target"] == "buyer@test.hr"

    async def test_send_invalid_delivery_method_returns_422(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                f"/api/erp/outbound-b2b/{uuid4()}/send",
                json={"delivery_method": "fax", "delivery_target": ""},
            )
        assert r.status_code == 422

    async def test_send_without_issue_returns_409(self, app):
        """Cannot send before issuing (approved → eracun_sent is not a valid transition)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_invoice(client)
            inv_id = doc["invoice_id"]
            await client.post(f"/api/erp/outbound-b2b/{inv_id}/approve")
            # Skip /issue step
            r = await client.post(
                f"/api/erp/outbound-b2b/{inv_id}/send",
                json={"delivery_method": "manual", "delivery_target": "x@x.hr"},
            )
        assert r.status_code == 409    # approved → eracun_sent not in SM


@_async_mark
class TestOutboundB2BDeliveredAccept:

    async def _issue_and_send(self, client) -> str:
        """Helper: create → approve → issue → send, return invoice_id."""
        doc = await _create_invoice(client)
        inv_id = doc["invoice_id"]
        await client.post(f"/api/erp/outbound-b2b/{inv_id}/approve")
        await client.post(f"/api/erp/outbound-b2b/{inv_id}/issue")
        await client.post(
            f"/api/erp/outbound-b2b/{inv_id}/send",
            json={"delivery_method": "manual", "delivery_target": "b@b.hr"},
        )
        return inv_id

    async def test_delivered_transitions(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            inv_id = await self._issue_and_send(client)
            r = await client.post(f"/api/erp/outbound-b2b/{inv_id}/delivered")
        assert r.status_code == 200
        assert r.json()["document_status"] == "delivered"

    async def test_accept_after_delivered(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            inv_id = await self._issue_and_send(client)
            await client.post(f"/api/erp/outbound-b2b/{inv_id}/delivered")
            r = await client.post(f"/api/erp/outbound-b2b/{inv_id}/accept")
        assert r.status_code == 200
        result = r.json()
        assert result["document_status"] == "accepted"
        assert result["accepted_at"] is not None

    async def test_accept_is_terminal(self, app):
        """Cannot transition out of accepted."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            inv_id = await self._issue_and_send(client)
            await client.post(f"/api/erp/outbound-b2b/{inv_id}/delivered")
            await client.post(f"/api/erp/outbound-b2b/{inv_id}/accept")
            r = await client.post(f"/api/erp/outbound-b2b/{inv_id}/accept")
        assert r.status_code == 409    # accepted is terminal


@_async_mark
class TestOutboundB2BReject:

    async def _issue_and_send(self, client) -> str:
        doc = await _create_invoice(client)
        inv_id = doc["invoice_id"]
        await client.post(f"/api/erp/outbound-b2b/{inv_id}/approve")
        await client.post(f"/api/erp/outbound-b2b/{inv_id}/issue")
        await client.post(
            f"/api/erp/outbound-b2b/{inv_id}/send",
            json={"delivery_method": "manual", "delivery_target": ""},
        )
        return inv_id

    async def test_reject_from_eracun_sent(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            inv_id = await self._issue_and_send(client)
            r = await client.post(
                f"/api/erp/outbound-b2b/{inv_id}/reject",
                json={"rejection_reason": "Pogrešan iznos PDV-a."},
            )
        assert r.status_code == 200
        result = r.json()
        assert result["document_status"] == "rejected"
        assert result["rejection_reason"] == "Pogrešan iznos PDV-a."

    async def test_reject_requires_reason(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            inv_id = await self._issue_and_send(client)
            r = await client.post(
                f"/api/erp/outbound-b2b/{inv_id}/reject",
                json={"rejection_reason": ""},
            )
        assert r.status_code == 422

    async def test_rejected_is_terminal(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            inv_id = await self._issue_and_send(client)
            await client.post(
                f"/api/erp/outbound-b2b/{inv_id}/reject",
                json={"rejection_reason": "Neispravni podaci."},
            )
            r = await client.post(
                f"/api/erp/outbound-b2b/{inv_id}/reject",
                json={"rejection_reason": "Još jednom."},
            )
        assert r.status_code == 409    # rejected is terminal


@_async_mark
class TestOutboundB2BCancel:

    async def test_cancel_draft(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_invoice(client)
            r = await client.post(f"/api/erp/outbound-b2b/{doc['invoice_id']}/cancel")
        assert r.status_code == 200
        assert r.json()["document_status"] == "cancelled"

    async def test_cancel_approved(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_invoice(client)
            inv_id = doc["invoice_id"]
            await client.post(f"/api/erp/outbound-b2b/{inv_id}/approve")
            r = await client.post(f"/api/erp/outbound-b2b/{inv_id}/cancel")
        assert r.status_code == 200
        assert r.json()["document_status"] == "cancelled"


@_async_mark
class TestOutboundB2BArchive:

    _mock_nav = None

    @staticmethod
    def _make_mock_nav():
        nav = MagicMock()
        nav.get_folder_id = MagicMock(return_value="archive-out-b2b-folder-id")
        return nav

    async def test_archive_after_issue(self, app):
        """Archive uploads UBL + meta to Drive (mocked) and returns archive metadata."""
        mock_nav = self._make_mock_nav()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_invoice(client)
            inv_id = doc["invoice_id"]
            await client.post(f"/api/erp/outbound-b2b/{inv_id}/approve")
            await client.post(f"/api/erp/outbound-b2b/{inv_id}/issue")

            with (
                patch("tools.drive_navigator.get_drive_navigator",
                      new=AsyncMock(return_value=mock_nav)),
                patch("services.erp.outbound_archive_service._upload_bytes_to_drive",
                      new=AsyncMock(return_value={"id": "drive-file-123", "name": "ubl.xml"})),
                patch("services.erp.outbound_archive_service._get_or_create_folder",
                      new=AsyncMock(return_value="month-folder-id")),
                patch("tools.google_api_client.create_api_client_auto",
                      return_value=MagicMock(credentials=MagicMock())),
            ):
                r = await client.post(f"/api/erp/outbound-b2b/{inv_id}/archive")

        assert r.status_code == 200
        result = r.json()
        assert result["archive_status"] == "archived"
        assert result["archive_folder_id"] is not None
        assert result["archived_at"] is not None

    async def test_archive_without_ubl_returns_422(self, app):
        """Cannot archive a draft invoice (no UBL generated)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_invoice(client)
            r = await client.post(f"/api/erp/outbound-b2b/{doc['invoice_id']}/archive")
        assert r.status_code == 422
        assert r.json()["code"] == "UBL_NOT_GENERATED"

    async def test_archive_idempotent(self, app):
        """Second archive call returns current archived state (idempotent)."""
        mock_nav = self._make_mock_nav()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_invoice(client)
            inv_id = doc["invoice_id"]
            await client.post(f"/api/erp/outbound-b2b/{inv_id}/approve")
            await client.post(f"/api/erp/outbound-b2b/{inv_id}/issue")

            with (
                patch("tools.drive_navigator.get_drive_navigator",
                      new=AsyncMock(return_value=mock_nav)),
                patch("services.erp.outbound_archive_service._upload_bytes_to_drive",
                      new=AsyncMock(return_value={"id": "drive-file-999", "name": "ubl.xml"})),
                patch("services.erp.outbound_archive_service._get_or_create_folder",
                      new=AsyncMock(return_value="month-folder-id")),
                patch("tools.google_api_client.create_api_client_auto",
                      return_value=MagicMock(credentials=MagicMock())),
            ):
                await client.post(f"/api/erp/outbound-b2b/{inv_id}/archive")
                # Second call — early-returns without hitting Drive
                r = await client.post(f"/api/erp/outbound-b2b/{inv_id}/archive")

        assert r.status_code == 200
        assert r.json()["archive_status"] == "archived"


# ── Full end-to-end lifecycle ────────────────────────────────────────────────

@_async_mark
class TestOutboundB2BEndToEnd:

    async def test_full_lifecycle_draft_to_accepted(self, app):
        """
        Full happy path:
          create (draft) → approve → issue → send → delivered → accept
        """
        mock_nav = MagicMock()
        mock_nav.get_folder_id = MagicMock(return_value="archive-folder-id")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. Create
            doc = await _create_invoice(client)
            inv_id = doc["invoice_id"]
            assert doc["document_status"] == "draft"

            # 2. Approve
            r = await client.post(f"/api/erp/outbound-b2b/{inv_id}/approve")
            assert r.json()["document_status"] == "approved"

            # 3. Issue (UBL generated)
            r = await client.post(f"/api/erp/outbound-b2b/{inv_id}/issue")
            assert r.json()["document_status"] == "issued"
            assert r.json()["ubl_xml"] is not None

            # 4. Send
            r = await client.post(
                f"/api/erp/outbound-b2b/{inv_id}/send",
                json={"delivery_method": "manual", "delivery_target": "kupac@firma.hr"},
            )
            assert r.json()["document_status"] == "eracun_sent"

            # 5. Delivered
            r = await client.post(f"/api/erp/outbound-b2b/{inv_id}/delivered")
            assert r.json()["document_status"] == "delivered"

            # 6. Accept
            r = await client.post(f"/api/erp/outbound-b2b/{inv_id}/accept")
            final = r.json()

        assert final["document_status"] == "accepted"
        assert final["accepted_at"] is not None
        assert final["sent_at"] is not None
        assert final["delivered_at"] is not None
        # Verify via GET as well
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get(f"/api/erp/outbound-b2b/{inv_id}")
        assert r.json()["document_status"] == "accepted"


# ── Payment integration: invoices_b2b is a first-class ERP invoice ───────────

@_async_mark
class TestOutboundB2BPayment:
    """
    Verify that InvoiceService.record_payment() works against invoices_b2b docs.
    This confirms that outbound B2B invoices are true ERP objects, not orphaned docs.
    """

    async def _create_issued_invoice(self, client) -> dict:
        """Create → approve → issue, return doc (contains invoice_id)."""
        doc = await _create_invoice(client)
        inv_id = doc["invoice_id"]
        await client.post(f"/api/erp/outbound-b2b/{inv_id}/approve")
        r = await client.post(f"/api/erp/outbound-b2b/{inv_id}/issue")
        return r.json()

    async def test_payment_recorded_via_invoice_service(self, app):
        """
        POST /api/erp/invoices/b2b/{id}/payment must succeed and update
        erp_amount_paid / erp_payment_status on the invoices_b2b doc.
        """
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await self._create_issued_invoice(client)
            inv_id = doc["invoice_id"]
            total_gross = doc["total_gross"]

            # Record a partial payment via the shared invoice payment endpoint
            payment_amount = round(total_gross / 2, 2)
            r = await client.post(
                f"/api/erp/invoices/b2b/{inv_id}/payment",
                json={
                    "amount": payment_amount,
                    "payment_date": "2026-04-05",
                    "payment_method": "transfer",
                    "reference": "HR00 1234-567",
                },
            )

        assert r.status_code == 200, r.text
        result = r.json()
        assert result["new_payment_status"] == "partial"
        assert abs(result["amount_due_after"] - (total_gross - payment_amount)) < 0.02

    async def test_full_payment_marks_paid(self, app):
        """Full payment transitions erp_payment_status to 'paid'."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await self._create_issued_invoice(client)
            inv_id = doc["invoice_id"]
            total_gross = doc["total_gross"]

            r = await client.post(
                f"/api/erp/invoices/b2b/{inv_id}/payment",
                json={
                    "amount": total_gross,
                    "payment_date": "2026-04-05",
                    "payment_method": "transfer",
                    "reference": "HR00 9999-001",
                },
            )

        assert r.status_code == 200, r.text
        assert r.json()["new_payment_status"] == "paid"
        assert r.json()["amount_due_after"] == 0.0

    async def test_overpayment_rejected(self, app):
        """Cannot pay more than the invoice total."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await self._create_issued_invoice(client)
            inv_id = doc["invoice_id"]
            total_gross = doc["total_gross"]

            r = await client.post(
                f"/api/erp/invoices/b2b/{inv_id}/payment",
                json={
                    "amount": total_gross + 1.00,
                    "payment_date": "2026-04-05",
                    "payment_method": "cash",
                    "reference": "",
                },
            )

        assert r.status_code == 422
        assert r.json()["code"] == "OVERPAYMENT"
