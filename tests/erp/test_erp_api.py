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
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── Minimal ERP app for testing (no agent system, no lifespan) ──────────────

def build_test_app(company_id: str) -> FastAPI:
    """
    Build a minimal FastAPI app with only ERP routes.
    Bypasses the full lifespan / agent system initialization.
    """
    from fastapi.responses import JSONResponse
    from fastapi import Request
    from services.erp.errors import BusinessError
    from services.erp.repositories.base import InvoiceReference
    from web.models import PaymentRequest, VendorInvoiceCreate, StockAdjustRequest, CustomerCreate, ProductCreate

    app = FastAPI()

    @app.exception_handler(BusinessError)
    async def business_error_handler(request: Request, exc: BusinessError):
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message, "field": exc.field},
        )

    import uuid as _uuid
    from services.erp.request_context import ERPRequestContext

    def _ctx():
        return ERPRequestContext(
            user_id="test-user",
            company_id=company_id,
            role="owner",
            grants=set(),
            denies=set(),
            request_id=str(_uuid.uuid4()),
        )

    @app.get("/api/erp/me")
    async def erp_me():
        ctx = _ctx()
        return {"user_id": ctx.user_id, "company_id": ctx.company_id, "role": ctx.role}

    @app.get("/api/erp/customers")
    async def erp_list_customers(limit: int = 20, offset: int = 0):
        from services.erp.customer_service import get_customer_service
        return await get_customer_service().list_customers(_ctx(), limit=limit, offset=offset)

    @app.post("/api/erp/customers")
    async def erp_create_customer(req: CustomerCreate):
        from services.erp.customer_service import get_customer_service
        return await get_customer_service().create_customer(req.dict(), _ctx())

    @app.get("/api/erp/reports/vat")
    async def erp_vat_report(year: int = 2026, month: int = 1):
        from services.erp.reporting_service import get_reporting_service
        return await get_reporting_service().get_vat_summary(_ctx(), year, month)

    @app.get("/api/erp/payments/{payment_id}/allocations")
    async def erp_payment_allocations(payment_id: str):
        from services.erp.payment_service import get_payment_service
        return await get_payment_service().get_allocations_for_payment(payment_id, _ctx())

    @app.get("/api/erp/invoices/{invoice_type}/{invoice_id}/allocations")
    async def erp_invoice_allocations(invoice_type: str, invoice_id: str):
        from services.erp.payment_service import get_payment_service
        return await get_payment_service().get_allocations_for_invoice(invoice_id, _ctx())

    @app.post("/api/erp/invoices/{invoice_type}/{invoice_id}/payment")
    async def erp_record_payment(invoice_type: str, invoice_id: str, req: PaymentRequest):
        from services.erp.invoice_service import get_invoice_service
        ctx = _ctx()
        invoice_svc = get_invoice_service()
        ref_tmp = InvoiceReference(invoice_id=invoice_id, invoice_type=invoice_type, display_id=invoice_id)
        try:
            invoice_doc = await invoice_svc.get_invoice(ref_tmp, ctx)
            real_display_id = (
                invoice_doc.get("invoice_number") or invoice_doc.get("display_id") or invoice_id
            )
        except Exception:
            real_display_id = invoice_id
        ref = InvoiceReference(invoice_id=invoice_id, invoice_type=invoice_type, display_id=real_display_id)
        return await invoice_svc.record_payment(
            invoice_ref=ref,
            amount=req.amount,
            payment_date=req.payment_date.isoformat(),
            payment_method=req.payment_method,
            reference=req.reference,
            ctx=ctx,
            idempotency_key=req.idempotency_key,
            notes=req.notes,
        )

    @app.post("/api/erp/vendor-invoices")
    async def erp_create_vendor_invoice(req: VendorInvoiceCreate):
        from services.erp.vendor_invoice_service import get_vendor_invoice_service
        return await get_vendor_invoice_service().create_vendor_invoice(req.dict(), _ctx())

    @app.get("/api/erp/vendor-invoices")
    async def erp_list_vendor_invoices(document_status: str = "", payment_status: str = "",
                                       vendor_id: str = "", limit: int = 50, offset: int = 0):
        from services.erp.vendor_invoice_service import get_vendor_invoice_service
        filters = {}
        if document_status: filters["document_status"] = document_status
        if payment_status: filters["payment_status"] = payment_status
        if vendor_id: filters["vendor_id"] = vendor_id
        return await get_vendor_invoice_service().list_vendor_invoices(_ctx(), filters, min(limit, 500), offset)

    @app.get("/api/erp/products/{product_id}/movements")
    async def erp_get_stock_movements(product_id: str, limit: int = 100):
        from services.erp.product_service import get_product_service
        return await get_product_service().get_stock_movements(product_id, _ctx(), min(limit, 500))

    @app.get("/api/erp/activity")
    async def erp_activity_feed(limit: int = 50):
        from services.erp.base_erp_service import get_firestore_db
        ctx = _ctx()
        db = get_firestore_db()
        query = (
            db.collection("audit_log")
            .where("company_id", "==", ctx.company_id)
            .where("target_service", "==", "erp")
            .order_by("timestamp", direction="DESCENDING")
            .limit(min(limit, 500))
        )
        events = []
        async for snap in query.stream():
            doc = snap.to_dict() or {}
            events.append({
                "id": snap.id, "timestamp": doc.get("timestamp"),
                "action": doc.get("action_type"), "description": doc.get("action_description"),
                "entity_type": doc.get("entity_type"), "display_id": doc.get("display_id"),
                "user_id": doc.get("user_id"),
            })
        return events

    @app.get("/api/erp/quotes")
    async def erp_list_quotes(document_status: str = "", limit: int = 50, offset: int = 0):
        from services.erp.quote_service import get_quote_service
        filters = {}
        if document_status: filters["document_status"] = document_status
        return await get_quote_service().list_quotes(_ctx(), filters, min(limit, 500), offset)

    @app.post("/api/erp/quotes")
    async def erp_create_quote(req: dict):
        from services.erp.quote_service import get_quote_service
        return await get_quote_service().create_quote(req, _ctx())

    @app.get("/api/erp/quotes/{quote_id}")
    async def erp_get_quote(quote_id: str):
        from services.erp.quote_service import get_quote_service
        return await get_quote_service().get_quote(quote_id, _ctx())

    @app.post("/api/erp/quotes/{quote_id}/send")
    async def erp_send_quote(quote_id: str):
        from services.erp.quote_service import get_quote_service
        return await get_quote_service().mark_sent(quote_id, _ctx())

    @app.post("/api/erp/quotes/{quote_id}/accept")
    async def erp_accept_quote(quote_id: str):
        from services.erp.quote_service import get_quote_service
        return await get_quote_service().accept_quote(quote_id, _ctx())

    @app.post("/api/erp/quotes/{quote_id}/convert")
    async def erp_convert_quote(quote_id: str, req: dict):
        from services.erp.quote_service import get_quote_service
        return await get_quote_service().convert_to_invoice(quote_id, req.get("invoice_type", "b2c"), _ctx())

    @app.get("/api/erp/quotes/{quote_id}/print")
    async def erp_print_quote(quote_id: str):
        from services.erp.quote_service import get_quote_service
        from fastapi.responses import HTMLResponse
        q = await get_quote_service().get_quote(quote_id, _ctx())
        return HTMLResponse(content=f"<html><body><h1>{q.get('display_id','')}</h1></body></html>")

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
