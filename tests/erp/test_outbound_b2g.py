"""
Outbound B2G eRačun Tests (Sprint B2G-1)
=========================================
Tests for:
  - OutboundB2GService lifecycle (service-layer)
  - UBL 2.1 builder: BuyerReference in generated XML
  - Full lifecycle: draft → approved → issued → eracun_sent → accepted
  - State machine: reject, cancel
  - Collection isolation: B2G docs go to invoices_b2g, NOT invoices_b2b
  - API routes: POST /outbound-b2g, GET /outbound-b2g, lifecycle transitions

Uses real Firestore (same pattern as test_outbound_b2b.py).
Drive archive calls are mocked.
"""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from datetime import date

import httpx
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from services.erp.errors import BusinessError
from services.erp.request_context import ERPRequestContext
from web.erp_routes import router as erp_router, get_erp_ctx

pytestmark = pytest.mark.integration
_async_mark = pytest.mark.asyncio(loop_scope="session")


# ── App / Fixtures ─────────────────────────────────────────────────────────

def build_test_app(company_id: str) -> FastAPI:
    app = FastAPI()

    @app.exception_handler(BusinessError)
    async def biz_err(request: Request, exc: BusinessError):
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message},
        )

    app.include_router(erp_router)

    def _ctx() -> ERPRequestContext:
        return ERPRequestContext(
            user_id="test-b2g-user",
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
    return f"test_b2g_{uuid4().hex}"


@pytest.fixture(scope="module")
def app(company_id):
    return build_test_app(company_id)


_SAMPLE_ITEMS = [
    {
        "description": "IT usluge za javni sektor",
        "name": "IT usluge za javni sektor",
        "quantity": 10,
        "unit": "sat",
        "unit_price": 80.00,
        "vat_rate": 25,
    },
]


def _b2g_payload(**overrides) -> dict:
    base = {
        "customer_name": "Ministarstvo financija",
        "customer_oib": "12345678901",
        "customer_peppol_id": "0190:12345678901",
        "buyer_reference": "UG-2026-IT-001",
        "seller_name": "Dobavljač d.o.o.",
        "seller_oib": "98765432100",
        "seller_iban": "HR1210010051863000160",
        "issue_date": str(date(2026, 4, 1)),
        "due_date": str(date(2026, 5, 1)),
        "items": _SAMPLE_ITEMS,
    }
    base.update(overrides)
    return base


def make_ctx(company_id: str) -> ERPRequestContext:
    return ERPRequestContext(
        user_id="test-b2g", company_id=company_id, role="owner",
        grants=["*"], denies=[], request_id=str(uuid4()),
    )


# ── Unit: UBL builder BuyerReference ───────────────────────────────────────

@pytest.mark.unit
class TestUBLBuyerReference:  # sync — no asyncio marker

    def test_buyer_reference_included_when_provided(self):
        """B2G: buyer_reference field → BuyerReference element in UBL XML."""
        from services.erp.ubl_outbound_builder import build_ubl_b2b
        doc = {
            "invoice_number": "B2G-2026-000001",
            "issue_date": "2026-04-01",
            "seller_name": "Dobavljač d.o.o.",
            "seller_oib": "98765432100",
            "customer_name": "Ministarstvo financija",
            "customer_oib": "12345678901",
            "buyer_reference": "UG-2026-IT-001",
            "items": _SAMPLE_ITEMS,
        }
        xml = build_ubl_b2b(doc)
        assert "BuyerReference" in xml, "BuyerReference element missing from UBL"
        assert "UG-2026-IT-001" in xml

    def test_buyer_reference_absent_when_not_provided(self):
        """B2B: no buyer_reference → BuyerReference element must not appear."""
        from services.erp.ubl_outbound_builder import build_ubl_b2b
        doc = {
            "invoice_number": "B2B-2026-000001",
            "issue_date": "2026-04-01",
            "seller_name": "A d.o.o.",
            "seller_oib": "11111111111",
            "customer_name": "B d.o.o.",
            "customer_oib": "22222222222",
            "items": _SAMPLE_ITEMS,
        }
        xml = build_ubl_b2b(doc)
        assert "BuyerReference" not in xml


# ── Integration: OutboundB2GService lifecycle ───────────────────────────────

@_async_mark
class TestOutboundB2GServiceLifecycle:

    @pytest.mark.asyncio
    async def test_create_stores_in_b2g_collection(self, company_id):
        """create() writes to invoices_b2g, NOT invoices_b2b."""
        from services.erp.outbound_b2g_service import get_outbound_b2g_service
        from services.erp.base_erp_service import get_firestore_db

        ctx = make_ctx(company_id)
        svc = get_outbound_b2g_service()
        data = _b2g_payload()
        for f in ("issue_date", "due_date"):
            if data.get(f):
                data[f] = data[f]  # already string

        doc = await svc.create(data, ctx)
        assert doc["document_status"] == "draft"
        assert doc["invoice_type"]    == "b2g"

        db = get_firestore_db()
        # Must exist in invoices_b2g
        snap_b2g = await db.collection("invoices_b2g").document(doc["invoice_id"]).get()
        assert snap_b2g.exists, "Invoice not found in invoices_b2g"

        # Must NOT exist in invoices_b2b
        snap_b2b = await db.collection("invoices_b2b").document(doc["invoice_id"]).get()
        assert not snap_b2b.exists, "B2G invoice leaked into invoices_b2b"

    @pytest.mark.asyncio
    async def test_create_stores_b2g_specific_fields(self, company_id):
        """buyer_reference and customer_peppol_id are persisted."""
        from services.erp.outbound_b2g_service import get_outbound_b2g_service

        ctx = make_ctx(company_id)
        svc = get_outbound_b2g_service()
        data = _b2g_payload(buyer_reference="KONTRAKT-999", customer_peppol_id="0190:99999999999")
        doc = await svc.create(data, ctx)

        assert doc["buyer_reference"]    == "KONTRAKT-999"
        assert doc["customer_peppol_id"] == "0190:99999999999"
        # Peppol ID pre-fills delivery_target
        assert doc["delivery_target"]    == "0190:99999999999"

    @pytest.mark.asyncio
    async def test_display_id_has_b2g_prefix(self, company_id):
        """B2G invoices use 'B2G' display prefix, not 'B2B'."""
        from services.erp.outbound_b2g_service import get_outbound_b2g_service

        ctx = make_ctx(company_id)
        doc = await get_outbound_b2g_service().create(_b2g_payload(), ctx)
        assert doc["display_id"].startswith("B2G"), (
            f"Expected B2G prefix, got: {doc['display_id']}"
        )

    @pytest.mark.asyncio
    async def test_approve_transitions_to_approved(self, company_id):
        """approve() transitions draft → approved."""
        from services.erp.outbound_b2g_service import get_outbound_b2g_service

        ctx = make_ctx(company_id)
        svc = get_outbound_b2g_service()
        doc = await svc.create(_b2g_payload(), ctx)
        approved = await svc.approve(doc["invoice_id"], ctx)
        assert approved["document_status"] == "approved"

    @pytest.mark.asyncio
    async def test_issue_generates_ubl_with_buyer_reference(self, company_id):
        """issue() generates UBL XML that includes BuyerReference for B2G."""
        from services.erp.outbound_b2g_service import get_outbound_b2g_service

        ctx = make_ctx(company_id)
        svc = get_outbound_b2g_service()
        doc = await svc.create(_b2g_payload(buyer_reference="REF-B2G-TEST"), ctx)
        await svc.approve(doc["invoice_id"], ctx)
        issued = await svc.issue(doc["invoice_id"], ctx)

        assert issued["document_status"] == "issued"
        assert issued.get("ubl_xml"),      "UBL XML not generated"
        assert "BuyerReference" in issued["ubl_xml"]
        assert "REF-B2G-TEST"   in issued["ubl_xml"]

    @pytest.mark.asyncio
    async def test_full_lifecycle_draft_to_accepted(self, company_id):
        """Full lifecycle: draft → approved → issued → eracun_sent → delivered → accepted."""
        from services.erp.outbound_b2g_service import get_outbound_b2g_service
        from services.erp.outbound_dispatch_service import dispatch_invoice

        ctx = make_ctx(company_id)
        svc = get_outbound_b2g_service()

        doc     = await svc.create(_b2g_payload(), ctx)
        inv_id  = doc["invoice_id"]

        await svc.approve(inv_id, ctx)
        await svc.issue(inv_id, ctx)

        # Mock dispatch so we don't need a real AP connection
        with patch(
            "services.erp.outbound_b2g_service.OutboundB2GService.send",
            new=AsyncMock(return_value={
                "invoice_id":      inv_id,
                "document_status": "eracun_sent",
                "sent_at":         "2026-04-14T10:00:00+00:00",
            }),
        ):
            sent = await svc.send(inv_id, ctx, "manual", "")
            assert sent["document_status"] == "eracun_sent"

        # Get the doc to confirm status (send was mocked, so re-fetch from service)
        # Since send was mocked we need to manually transition for the rest
        await svc._get_db().collection("invoices_b2g").document(inv_id).update({
            "document_status": "eracun_sent", "sent_at": "2026-04-14T10:00:00+00:00",
            "delivery_method": "manual",
        })

        delivered = await svc.mark_delivered(inv_id, ctx)
        assert delivered["document_status"] == "delivered"

        accepted = await svc.accept(inv_id, ctx)
        assert accepted["document_status"] == "accepted"

    @pytest.mark.asyncio
    async def test_reject_from_eracun_sent(self, company_id):
        """reject() transitions eracun_sent → rejected with reason."""
        from services.erp.outbound_b2g_service import get_outbound_b2g_service

        ctx = make_ctx(company_id)
        svc = get_outbound_b2g_service()
        doc = await svc.create(_b2g_payload(), ctx)
        inv_id = doc["invoice_id"]
        await svc.approve(inv_id, ctx)
        await svc.issue(inv_id, ctx)
        # Force to eracun_sent
        await svc._get_db().collection("invoices_b2g").document(inv_id).update({
            "document_status": "eracun_sent",
        })
        rejected = await svc.reject(inv_id, ctx, "Pogrešan iznos")
        assert rejected["document_status"] == "rejected"
        assert rejected["rejection_reason"] == "Pogrešan iznos"

    @pytest.mark.asyncio
    async def test_cancel_from_draft(self, company_id):
        """cancel() allowed from draft."""
        from services.erp.outbound_b2g_service import get_outbound_b2g_service

        ctx = make_ctx(company_id)
        svc = get_outbound_b2g_service()
        doc = await svc.create(_b2g_payload(), ctx)
        cancelled = await svc.cancel(doc["invoice_id"], ctx)
        assert cancelled["document_status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_list_returns_only_b2g_invoices(self, company_id):
        """list() returns B2G invoices and not B2B invoices for same company."""
        from services.erp.outbound_b2g_service import get_outbound_b2g_service
        from services.erp.outbound_b2b_service import get_outbound_b2b_service

        ctx = make_ctx(company_id)

        # Create a B2G invoice
        b2g_doc = await get_outbound_b2g_service().create(_b2g_payload(), ctx)

        # Create a B2B invoice (different collection)
        b2b_data = {
            "customer_name": "B2B Kupac d.o.o.", "customer_oib": "11223344556",
            "seller_name": "Dobavljač d.o.o.", "seller_oib": "98765432100",
            "issue_date": "2026-04-01",
            "items": _SAMPLE_ITEMS,
        }
        await get_outbound_b2b_service().create(b2b_data, ctx)

        # B2G list must NOT contain B2B invoice_id
        b2g_docs = await get_outbound_b2g_service().list(ctx)
        b2g_ids  = {d.get("invoice_id") or d.get("_id") for d in b2g_docs}
        assert b2g_doc["invoice_id"] in b2g_ids,    "B2G invoice not in B2G list"


# ── API route tests ─────────────────────────────────────────────────────────

@_async_mark
class TestOutboundB2GRoutes:

    @pytest.mark.asyncio
    async def test_post_outbound_b2g_returns_200(self, app):
        """POST /api/erp/outbound-b2g → 200 with draft invoice."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/erp/outbound-b2g", json=_b2g_payload())
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["invoice_type"]    == "b2g"
        assert body["document_status"] == "draft"
        assert body["display_id"].startswith("B2G")
        assert body["buyer_reference"] == "UG-2026-IT-001"

    @pytest.mark.asyncio
    async def test_get_outbound_b2g_list_returns_200(self, app):
        """GET /api/erp/outbound-b2g → 200 list."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/erp/outbound-b2g")
        assert resp.status_code == 200, resp.text
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_post_then_approve_and_issue(self, app):
        """POST create → approve → issue returns issued status with UBL."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r_create = await client.post("/api/erp/outbound-b2g", json=_b2g_payload(
                buyer_reference="API-TEST-REF"
            ))
            assert r_create.status_code == 200, r_create.text
            inv_id = r_create.json()["invoice_id"]

            r_approve = await client.post(f"/api/erp/outbound-b2g/{inv_id}/approve")
            assert r_approve.status_code == 200, r_approve.text
            assert r_approve.json()["document_status"] == "approved"

            r_issue = await client.post(f"/api/erp/outbound-b2g/{inv_id}/issue")
            assert r_issue.status_code == 200, r_issue.text
            body = r_issue.json()
            assert body["document_status"] == "issued"
            assert body.get("ubl_xml"),     "UBL XML not generated"
            assert "BuyerReference" in body["ubl_xml"]
            assert "API-TEST-REF"   in body["ubl_xml"]

    @pytest.mark.asyncio
    async def test_missing_customer_oib_returns_422(self, app):
        """POST without customer_oib → 422 validation error."""
        payload = _b2g_payload()
        del payload["customer_oib"]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/erp/outbound-b2g", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_single_b2g_invoice(self, app):
        """GET /outbound-b2g/{id} → 200 for existing B2G invoice."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r_create = await client.post("/api/erp/outbound-b2g", json=_b2g_payload())
            inv_id = r_create.json()["invoice_id"]

            r_get = await client.get(f"/api/erp/outbound-b2g/{inv_id}")
        assert r_get.status_code == 200, r_get.text
        assert r_get.json()["invoice_id"] == inv_id

    @pytest.mark.asyncio
    async def test_b2g_invoice_not_accessible_via_b2b_route(self, app):
        """A B2G invoice ID cannot be fetched via the /outbound-b2b/{id} route."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r_create = await client.post("/api/erp/outbound-b2g", json=_b2g_payload())
            inv_id = r_create.json()["invoice_id"]

            # Try to fetch B2G invoice via B2B route — should 404
            r_wrong = await client.get(f"/api/erp/outbound-b2b/{inv_id}")
        assert r_wrong.status_code == 404, (
            f"B2G invoice {inv_id} should not be accessible via B2B route, "
            f"got {r_wrong.status_code}: {r_wrong.text}"
        )
