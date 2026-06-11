"""
Outbound B2B Capability Model Tests (Faza 2D)
===============================================
Tests for:
  - ADAPTER_CAPABILITIES map structure                [unit]
  - get_capabilities() / ack_expected() helpers       [unit]
  - pending-ack filters by ack_expected               [integration]
  - GET /outbound-b2b/capabilities                    [API]
  - delivery_capabilities snapshot stored on send()   [integration]
"""

import pytest
from uuid import uuid4
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

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
            user_id="test-user-cap",
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
    return f"test_cap_{uuid4().hex}"


@pytest.fixture(scope="module")
def app(company_id):
    return build_test_app(company_id)


# ── Helpers ──────────────────────────────────────────────────────────────────

_SAMPLE_ITEMS = [
    {
        "description": "Usluga",
        "name": "Usluga",
        "quantity": 2,
        "unit": "kom",
        "unit_price": 100.0,
        "vat_rate": 25,
    }
]


def _b2b_payload(**overrides) -> dict:
    base = {
        "customer_name": "Kupac d.o.o.",
        "customer_oib": "12345678901",
        "seller_name": "Prodavač d.o.o.",
        "seller_oib": "98765432100",
        "seller_iban": "HR1210010051863000160",
        "issue_date": str(date(2026, 4, 1)),
        "items": _SAMPLE_ITEMS,
    }
    base.update(overrides)
    return base


async def _create_and_issue(client) -> dict:
    r = await client.post("/api/erp/outbound-b2b", json=_b2b_payload())
    assert r.status_code == 200
    inv_id = r.json()["invoice_id"]
    await client.post(f"/api/erp/outbound-b2b/{inv_id}/approve")
    r2 = await client.post(f"/api/erp/outbound-b2b/{inv_id}/issue")
    assert r2.status_code == 200
    return r2.json()


# ── Unit tests: capability map ────────────────────────────────────────────────

@pytest.mark.unit
class TestCapabilityMap:
    """Sync unit tests."""

    def test_all_known_methods_present(self):
        from services.erp.outbound_capabilities import ADAPTER_CAPABILITIES
        assert "manual" in ADAPTER_CAPABILITIES
        assert "email" in ADAPTER_CAPABILITIES
        assert "peppol" in ADAPTER_CAPABILITIES

    def test_each_entry_has_required_keys(self):
        from services.erp.outbound_capabilities import ADAPTER_CAPABILITIES
        required = {"can_dispatch", "auto_ack", "polling", "ack_expected", "description"}
        for method, caps in ADAPTER_CAPABILITIES.items():
            missing = required - caps.keys()
            assert not missing, f"Method {method!r} missing keys: {missing}"

    def test_manual_ack_not_expected(self):
        from services.erp.outbound_capabilities import ack_expected
        assert ack_expected("manual") is False

    def test_email_ack_expected(self):
        from services.erp.outbound_capabilities import ack_expected
        assert ack_expected("email") is True

    def test_peppol_ack_expected(self):
        from services.erp.outbound_capabilities import ack_expected
        assert ack_expected("peppol") is True

    def test_peppol_polling_supported(self):
        from services.erp.outbound_capabilities import polling_supported
        assert polling_supported("peppol") is True

    def test_manual_polling_not_supported(self):
        from services.erp.outbound_capabilities import polling_supported
        assert polling_supported("manual") is False

    def test_unknown_method_falls_back_to_manual(self):
        from services.erp.outbound_capabilities import get_capabilities
        caps = get_capabilities("fax_machine_1995")
        # Should return manual defaults (safest)
        assert caps["ack_expected"] is False

    def test_get_capabilities_returns_dict(self):
        from services.erp.outbound_capabilities import get_capabilities
        caps = get_capabilities("email")
        assert isinstance(caps, dict)
        assert caps["can_dispatch"] is True


# ── API: GET /outbound-b2b/capabilities ──────────────────────────────────────

@_async_mark
class TestCapabilitiesEndpoint:

    async def test_capabilities_returns_200(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/erp/outbound-b2b/capabilities")
        assert r.status_code == 200

    async def test_capabilities_has_all_methods(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/erp/outbound-b2b/capabilities")
        data = r.json()
        assert "manual" in data
        assert "email"  in data
        assert "peppol" in data

    async def test_capabilities_entries_have_required_fields(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/erp/outbound-b2b/capabilities")
        for method, caps in r.json().items():
            assert "can_dispatch"  in caps, f"{method}: missing can_dispatch"
            assert "ack_expected"  in caps, f"{method}: missing ack_expected"
            assert "description"   in caps, f"{method}: missing description"


# ── Integration: delivery_capabilities snapshot on doc ───────────────────────

@_async_mark
class TestDeliveryCapabilitiesStoredOnSend:

    async def test_new_doc_has_null_delivery_capabilities(self, app):
        """Before send(), delivery_capabilities must be None."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/api/erp/outbound-b2b", json=_b2b_payload())
        assert r.json()["delivery_capabilities"] is None

    async def test_send_stores_capabilities_snapshot(self, app):
        """After send(manual), delivery_capabilities must reflect manual adapter."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_and_issue(client)
            r = await client.post(
                f"/api/erp/outbound-b2b/{doc['invoice_id']}/send",
                json={"delivery_method": "manual", "delivery_target": ""},
            )
        assert r.status_code == 200
        caps = r.json().get("delivery_capabilities")
        assert caps is not None, "delivery_capabilities should be set after send()"
        assert caps["ack_expected"] is False
        assert caps["can_dispatch"] is True

    async def test_send_email_stores_email_capabilities(self, app):
        """After send(email), delivery_capabilities must reflect email adapter."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_and_issue(client)
            with (
                patch("tools.google_api_client.create_api_client_auto",
                      return_value=MagicMock(credentials=MagicMock())),
                patch("tools.api_implementations.gmail_api.gmail_send_message",
                      new=AsyncMock(return_value={"id": "gmail-ok", "status": "sent"})),
            ):
                r = await client.post(
                    f"/api/erp/outbound-b2b/{doc['invoice_id']}/send",
                    json={"delivery_method": "email", "delivery_target": "buyer@test.hr"},
                )
        assert r.status_code == 200
        caps = r.json().get("delivery_capabilities")
        assert caps is not None
        assert caps["ack_expected"] is True


# ── Integration: pending-ack filtered by ack_expected ────────────────────────

@_async_mark
class TestPendingAckCapabilityFiltering:

    async def test_manual_invoice_not_in_pending_ack(self, app):
        """
        Invoices sent via manual adapter should NOT appear in pending-ack
        (ack_expected=False — operator handles manually, no monitoring needed).
        """
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_and_issue(client)
            inv_id = doc["invoice_id"]
            await client.post(
                f"/api/erp/outbound-b2b/{inv_id}/send",
                json={"delivery_method": "manual", "delivery_target": ""},
            )
            r = await client.get("/api/erp/outbound-b2b/pending-ack")

        assert r.status_code == 200
        assert not any(d["invoice_id"] == inv_id for d in r.json()), (
            "Manual delivery invoices must not appear in pending-ack"
        )

    async def test_email_invoice_in_pending_ack(self, app):
        """Invoices sent via email (ack_expected=True) MUST appear in pending-ack."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_and_issue(client)
            inv_id = doc["invoice_id"]
            with (
                patch("tools.google_api_client.create_api_client_auto",
                      return_value=MagicMock(credentials=MagicMock())),
                patch("tools.api_implementations.gmail_api.gmail_send_message",
                      new=AsyncMock(return_value={"id": "gmail-ack-test"})),
            ):
                await client.post(
                    f"/api/erp/outbound-b2b/{inv_id}/send",
                    json={"delivery_method": "email", "delivery_target": "buyer@test.hr"},
                )
            r = await client.get("/api/erp/outbound-b2b/pending-ack")

        assert r.status_code == 200
        assert any(d["invoice_id"] == inv_id for d in r.json()), (
            "Email delivery invoice should appear in pending-ack"
        )
