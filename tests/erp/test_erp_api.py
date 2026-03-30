"""
ERP API Smoke Tests
====================
Tests the FastAPI ERP endpoints using httpx AsyncClient.

These tests use a REAL Firestore connection but with an isolated company_id
per test run. For full isolation, run against the Firestore emulator:
    firebase emulators:start --only firestore
    FIRESTORE_EMULATOR_HOST=localhost:8080 pytest tests/erp/test_erp_api.py

Without the emulator, set FIRESTORE_TEST_PROJECT to a separate test project,
or accept that tests will write to the same Firestore with test_{uuid} company_id.
"""

import pytest
import asyncio
from uuid import uuid4
from decimal import Decimal
from datetime import date

import httpx
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from services.erp.errors import BusinessError
from services.erp.request_context import ERPRequestContext
from web.erp_routes import router as erp_router, get_erp_ctx


def build_raw_app() -> FastAPI:
    """App with NO dependency override — tests the real get_erp_ctx auth flow."""
    app = FastAPI()

    @app.exception_handler(BusinessError)
    async def business_error_handler(request: Request, exc: BusinessError):
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message, "field": exc.field},
        )

    app.include_router(erp_router)
    return app


def build_test_app(company_id: str) -> FastAPI:
    """
    Build a minimal FastAPI app with the REAL ERP router from web/erp_routes.py.
    Uses dependency_overrides to inject test-specific ERPRequestContext.
    No agent system, no lifespan — just the ERP routes.
    """
    app = FastAPI()

    @app.exception_handler(BusinessError)
    async def business_error_handler(request: Request, exc: BusinessError):
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message, "field": exc.field},
        )

    app.include_router(erp_router)

    def _test_ctx() -> ERPRequestContext:
        return ERPRequestContext(
            user_id="test-user",
            company_id=company_id,
            role="owner",
            grants=["*"],
            denies=[],
            request_id=str(uuid4()),
        )

    app.dependency_overrides[get_erp_ctx] = _test_ctx
    return app


pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def company_id():
    """Unique company per test module run."""
    return f"test_{uuid4().hex}"


@pytest.fixture(scope="module")
def app(company_id):
    return build_test_app(company_id)


# ── Tests ────────────────────────────────────────────────────────────────────

class TestERPMe:
    @pytest.mark.asyncio
    async def test_me_returns_200_with_role(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/erp/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "owner"
        assert "company_id" in data


class TestCustomers:
    @pytest.mark.asyncio
    async def test_create_customer_returns_200(self, app):
        payload = {
            "name": f"Test Customer {uuid4().hex[:6]}",
            "oib": "",
            "party_type": "customer",
            "email": "",
            "phone": "",
            "address": "",
            "city": "",
            "country": "HR",
            "notes": "",
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/erp/customers", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "name" in data

    @pytest.mark.asyncio
    async def test_list_customers_returns_200(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/erp/customers")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestVendorInvoices:
    @pytest.mark.asyncio
    async def test_create_vendor_invoice_without_vendor_id_422(self, app):
        """Missing required fields → 422 REQUIRED_FIELD."""
        payload = {
            "vendor_id": "",
            "vendor_name": "",
            "vendor_oib": "",
            "vendor_invoice_no": "",
            "issue_date": str(date.today()),
            "received_date": str(date.today()),
            "due_date": str(date.today()),
            "total_gross": 100.0,
            "vat_amount": 20.0,
            "net_amount": 80.0,
            "currency": "EUR",
            "category": "other",
            "description": "",
            "notes": "",
            "line_items": [],
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/erp/vendor-invoices", json=payload)
        assert resp.status_code == 422


class TestInvoicePayment:
    @pytest.mark.asyncio
    async def test_payment_on_nonexistent_invoice_404(self, app):
        payload = {
            "amount": 100.0,
            "payment_date": str(date.today()),
            "payment_method": "transfer",
            "reference": "test",
            "idempotency_key": str(uuid4()),
            "notes": "",
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/erp/invoices/b2c/nonexistent-invoice-id/payment", json=payload)
        assert resp.status_code == 404


class TestReports:
    @pytest.mark.asyncio
    async def test_vat_report_returns_200(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/erp/reports/vat?year=2026&month=3")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("period") == "2026-03"


class TestAllocations:
    @pytest.mark.asyncio
    async def test_payment_allocations_returns_only_matching_payment_id(self, app):
        """Bug 1 fix: allocations endpoint must query by payment_id, not invoice_id."""
        fake_payment_id = str(uuid4())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/erp/payments/{fake_payment_id}/allocations")
        assert resp.status_code == 200
        allocations = resp.json()
        assert isinstance(allocations, list)
        # All returned allocations must match the queried payment_id
        for alloc in allocations:
            assert alloc.get("payment_id") == fake_payment_id

    @pytest.mark.asyncio
    async def test_invoice_allocations_route_exists(self, app):
        """Bug 1 fix: new route for allocations by invoice_id."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/erp/invoices/b2c/nonexistent-id/allocations")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestHardeningEdgeCases:
    """Edge case tests for empty states and invalid inputs."""

    @pytest.mark.asyncio
    async def test_activity_feed_empty_returns_list(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/erp/activity?limit=5")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_product_movements_nonexistent_returns_404(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/erp/products/nonexistent-id-xyz/movements")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_customer_list_empty_returns_list(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/erp/customers?search=NONEXISTENT_CUSTOMER_999")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_vendor_invoices_empty_returns_list(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/erp/vendor-invoices?document_status=cancelled")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_limit_clamped_to_max(self, app):
        """Verify that limit=9999 doesn't crash — clamped by _clamp_limit."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/erp/customers?limit=9999")
        assert resp.status_code == 200


class TestQuotesAPI:

    @pytest.mark.asyncio
    async def test_list_quotes_returns_200(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/erp/quotes")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_create_and_get_quote(self, app):
        payload = {
            "customer_id": "test-cust-123",
            "customer_name": "Test Kupac",
            "valid_until": "2026-12-31",
            "items": [{"description": "Widget", "quantity": 2, "unit_price": 50.0, "vat_rate": 25}],
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/erp/quotes", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["display_id"].startswith("PON-")
        assert data["document_status"] == "draft"
        assert data["total_gross"] == 125.0  # 2*50 * 1.25

        # Get the created quote
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp2 = await client.get(f"/api/erp/quotes/{data['_id']}")
        assert resp2.status_code == 200
        assert resp2.json()["display_id"] == data["display_id"]

    @pytest.mark.asyncio
    async def test_quote_e2e_create_send_accept_convert(self, app):
        """Full E2E: create → send → accept → convert to invoice."""
        payload = {
            "customer_id": "test-cust-e2e",
            "customer_name": "E2E Kupac",
            "valid_until": "2026-12-31",
            "items": [{"description": "Usluga", "quantity": 1, "unit_price": 100.0, "vat_rate": 25}],
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Create
            r = await client.post("/api/erp/quotes", json=payload)
            assert r.status_code == 200
            qid = r.json()["_id"]

            # Send
            r = await client.post(f"/api/erp/quotes/{qid}/send")
            assert r.status_code == 200
            assert r.json()["document_status"] == "sent"

            # Accept
            r = await client.post(f"/api/erp/quotes/{qid}/accept")
            assert r.status_code == 200
            assert r.json()["document_status"] == "accepted"

            # Convert
            r = await client.post(f"/api/erp/quotes/{qid}/convert", json={"invoice_type": "b2c"})
            assert r.status_code == 200
            result = r.json()
            assert result["already_converted"] is False
            assert result["invoice_display_id"].startswith("RA-")

            # Verify quote is converted
            r = await client.get(f"/api/erp/quotes/{qid}")
            assert r.json()["document_status"] == "converted"
            assert r.json()["converted_invoice_id"] == result["invoice_id"]

    @pytest.mark.asyncio
    async def test_print_quote_returns_html(self, app):
        """Print endpoint returns HTML with display_id."""
        payload = {
            "customer_id": "test-cust-print",
            "customer_name": "Print Kupac",
            "valid_until": "2026-12-31",
            "items": [{"description": "Stavka", "quantity": 1, "unit_price": 10.0, "vat_rate": 25}],
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/api/erp/quotes", json=payload)
            qid = r.json()["_id"]
            display_id = r.json()["display_id"]

            r = await client.get(f"/api/erp/quotes/{qid}/print")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
        assert display_id in r.text

    @pytest.mark.asyncio
    async def test_cancel_draft_quote(self, app):
        """Cancel a draft quote via API."""
        payload = {
            "customer_id": "test-cust-cancel",
            "customer_name": "Cancel Kupac",
            "valid_until": "2026-12-31",
            "items": [{"description": "Stavka", "quantity": 1, "unit_price": 50.0, "vat_rate": 25}],
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/api/erp/quotes", json=payload)
            qid = r.json()["_id"]

            r = await client.post(f"/api/erp/quotes/{qid}/cancel")
            assert r.status_code == 200
            assert r.json()["document_status"] == "cancelled"


# ── Auth Flow Tests (no dependency override — tests real get_erp_ctx) ────────

class TestAuthFlow:
    """Tests the real get_erp_ctx dependency: headers → erp_users lookup → context."""

    @pytest.mark.asyncio
    async def test_missing_headers_returns_401(self):
        """No identity headers → 401 Unauthorized."""
        raw_app = build_raw_app()
        async with AsyncClient(transport=ASGITransport(app=raw_app), base_url="http://test") as client:
            resp = await client.get("/api/erp/me")
        assert resp.status_code == 401
        assert "Missing" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_missing_company_header_returns_401(self):
        """User header present but no company → 401."""
        raw_app = build_raw_app()
        async with AsyncClient(transport=ASGITransport(app=raw_app), base_url="http://test") as client:
            resp = await client.get("/api/erp/me", headers={"X-ERP-User-Id": "someone"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_nonexistent_membership_returns_403(self):
        """Valid headers but user has no erp_users doc → 403."""
        raw_app = build_raw_app()
        headers = {
            "X-ERP-User-Id": f"ghost-user-{uuid4().hex}",
            "X-ERP-Company-Id": f"ghost-company-{uuid4().hex}",
        }
        async with AsyncClient(transport=ASGITransport(app=raw_app), base_url="http://test") as client:
            resp = await client.get("/api/erp/me", headers=headers)
        assert resp.status_code == 403
        assert "No active ERP membership" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_valid_membership_returns_200(self):
        """Seed an erp_users doc, send matching headers → 200 with correct context."""
        from services.erp.base_erp_service import get_firestore_db

        test_user_id = f"auth-test-{uuid4().hex[:8]}"
        test_company_id = f"test-co-{uuid4().hex[:8]}"

        db = get_firestore_db()
        doc_ref = db.collection("erp_users").document(f"{test_user_id}_{test_company_id}")
        await doc_ref.set({
            "user_id": test_user_id,
            "company_id": test_company_id,
            "role": "accountant",
            "email": "test@example.com",
            "display_name": "Test Accountant",
            "active": True,
            "permissions": {"grants": [], "denies": ["payment:record"]},
        })

        try:
            raw_app = build_raw_app()
            headers = {
                "X-ERP-User-Id": test_user_id,
                "X-ERP-Company-Id": test_company_id,
            }
            async with AsyncClient(transport=ASGITransport(app=raw_app), base_url="http://test") as client:
                resp = await client.get("/api/erp/me", headers=headers)

            assert resp.status_code == 200
            data = resp.json()
            assert data["user_id"] == test_user_id
            assert data["company_id"] == test_company_id
            assert data["role"] == "accountant"
        finally:
            # Cleanup
            await doc_ref.delete()

    @pytest.mark.asyncio
    async def test_inactive_user_returns_403(self):
        """User exists but active=False → 403."""
        from services.erp.base_erp_service import get_firestore_db

        test_user_id = f"inactive-{uuid4().hex[:8]}"
        test_company_id = f"test-co-{uuid4().hex[:8]}"

        db = get_firestore_db()
        doc_ref = db.collection("erp_users").document(f"{test_user_id}_{test_company_id}")
        await doc_ref.set({
            "user_id": test_user_id,
            "company_id": test_company_id,
            "role": "viewer",
            "active": False,
            "permissions": {"grants": [], "denies": []},
        })

        try:
            raw_app = build_raw_app()
            headers = {
                "X-ERP-User-Id": test_user_id,
                "X-ERP-Company-Id": test_company_id,
            }
            async with AsyncClient(transport=ASGITransport(app=raw_app), base_url="http://test") as client:
                resp = await client.get("/api/erp/me", headers=headers)
            assert resp.status_code == 403
        finally:
            await doc_ref.delete()
