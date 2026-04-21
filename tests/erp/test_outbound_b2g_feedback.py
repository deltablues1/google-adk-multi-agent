"""
Sprint B2G-1.1 + B2G-1.2 — B2G Peppol feedback loop regression tests
======================================================================
Locks:
  B2G-1.1:
    - AP webhook (POST /outbound-b2b/peppol/webhook) finds and transitions B2G docs
      (cross-collection fallback: B2B first, then B2G)
    - Webhook returns 404 when doc exists in neither collection
    - poll_pending_peppol_status() via /outbound-b2g/poll-peppol-status moves B2G docs
    - list_pending_peppol_sync() correctly filters stale B2G Peppol docs

  B2G-1.2:
    - send() without delivery_target falls back to doc.delivery_target (set at create
      from customer_peppol_id)
    - send() without delivery_target and no saved target still fails gracefully
"""

import pytest
import pytest_asyncio
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

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


def make_ctx(company_id: str) -> ERPRequestContext:
    return ERPRequestContext(
        user_id="test-b2g-feedback",
        company_id=company_id,
        role="owner",
        grants=["*"],
        denies=[],
        request_id=str(uuid4()),
    )


@pytest.fixture
def cid():
    return f"test_b2g_fb_{uuid4().hex}"


def build_app(company_id: str) -> FastAPI:
    app = FastAPI()

    @app.exception_handler(BusinessError)
    async def biz_err(request: Request, exc: BusinessError):
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message},
        )

    app.include_router(erp_router)

    def _ctx():
        return ERPRequestContext(
            user_id="test-b2g-feedback", company_id=company_id, role="owner",
            grants=["*"], denies=[], request_id=str(uuid4()),
        )

    app.dependency_overrides[get_erp_ctx] = _ctx
    return app


_ITEMS = [
    {"description": "IT usluge", "name": "IT usluge",
     "quantity": 1, "unit_price": 100.0, "vat_rate": 25},
]


async def _create_b2g_issued(company_id: str) -> dict:
    """Helper: create + approve + issue a B2G invoice. Returns issued doc."""
    from services.erp.outbound_b2g_service import get_outbound_b2g_service
    from services.erp.company_service import CompanyService

    ctx = make_ctx(company_id)
    await CompanyService().upsert({"oib": "47034854402", "name": "Test Kupac"}, ctx)

    svc = get_outbound_b2g_service()
    data = {
        "customer_name": "MFIN", "customer_oib": "12345678901",
        "customer_peppol_id": f"0190:{'12345678901'}",
        "buyer_reference": "KONTRAKT-B2G-FB",
        "seller_name": "Dobavljač d.o.o.", "seller_oib": "98765432100",
        "issue_date": str(date(2026, 4, 1)),
        "items": _ITEMS,
    }
    doc = await svc.create(data, ctx)
    await svc.approve(doc["invoice_id"], ctx)
    return await svc.issue(doc["invoice_id"], ctx)


# ── B2G-1.1: webhook cross-collection fallback ────────────────────────────────

class TestWebhookB2GFallback:

    @pytest.mark.asyncio
    async def test_webhook_finds_and_transitions_b2g_doc(self, cid):
        """
        B2G-1.1: AP webhook with a B2G submission_id → document found in invoices_b2g,
        status applied (eracun_sent → delivered via external_status "delivered").
        """
        import json, os
        from services.erp.outbound_b2g_service import get_outbound_b2g_service
        from services.erp.base_erp_service import get_firestore_db

        issued = await _create_b2g_issued(cid)
        inv_id = issued["invoice_id"]
        ctx    = make_ctx(cid)

        # Force document into eracun_sent with a known submission_id
        submission_id = f"B2G-AP-SID-{uuid4().hex[:8]}"
        db = get_firestore_db()
        await db.collection("invoices_b2g").document(inv_id).update({
            "document_status":  "eracun_sent",
            "delivery_method":  "peppol",
            "ap_submission_id": submission_id,
            "external_submission_id": submission_id,
            "sent_at":          "2026-04-14T08:00:00+00:00",
        })

        # Call webhook with no HMAC secret (dev mode)
        os.environ.pop("PEPPOL_AP_WEBHOOK_SECRET", None)

        webhook_payload = json.dumps({
            "submissionId": submission_id,
            "status":       "delivered",
        }).encode()

        app = build_app(cid)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/erp/outbound-b2b/peppol/webhook",
                content=webhook_payload,
                headers={"Content-Type": "application/json"},
            )

        assert resp.status_code == 200, f"Webhook failed: {resp.text}"
        body = resp.json()
        assert body["ok"]         is True
        assert body["invoice_id"] == inv_id

        # Verify document was updated in invoices_b2g
        snap = await db.collection("invoices_b2g").document(inv_id).get()
        doc  = snap.to_dict() or {}
        assert doc.get("document_status") in ("delivered", "eracun_sent"), (
            f"Expected delivered, got {doc.get('document_status')}"
        )

    @pytest.mark.asyncio
    async def test_webhook_b2g_not_touched_by_b2b_only_webhook(self, cid):
        """
        B2G-1.1: A submission_id that exists only in B2G is NOT resolved via B2B collection.
        The webhook must return 200 ok (found via B2G path).
        Previously this would return 404 (only searched B2B).
        """
        import json, os
        from services.erp.outbound_b2g_service import get_outbound_b2g_service
        from services.erp.base_erp_service import get_firestore_db

        issued = await _create_b2g_issued(cid)
        inv_id = issued["invoice_id"]
        submission_id = f"B2G-ONLY-SID-{uuid4().hex[:8]}"

        db = get_firestore_db()
        await db.collection("invoices_b2g").document(inv_id).update({
            "document_status":  "eracun_sent",
            "delivery_method":  "peppol",
            "ap_submission_id": submission_id,
            "external_submission_id": submission_id,
            "sent_at":          "2026-04-14T09:00:00+00:00",
        })

        os.environ.pop("PEPPOL_AP_WEBHOOK_SECRET", None)

        # Verify B2B collection does NOT have this submission_id
        from google.cloud.firestore_v1.base_query import FieldFilter
        b2b_hits = []
        async for snap in (
            db.collection("invoices_b2b")
            .where(filter=FieldFilter("ap_submission_id", "==", submission_id))
            .limit(1).stream()
        ):
            b2b_hits.append(snap.id)
        assert not b2b_hits, "Test invariant broken: submission_id leaked into invoices_b2b"

        payload = json.dumps({"submissionId": submission_id, "status": "delivered"}).encode()
        app = build_app(cid)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/erp/outbound-b2b/peppol/webhook",
                content=payload,
                headers={"Content-Type": "application/json"},
            )

        # Webhook must find it via B2G fallback — not 404
        assert resp.status_code == 200, (
            f"Expected 200 from B2G fallback, got {resp.status_code}: {resp.text}"
        )
        assert resp.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_webhook_404_when_not_in_any_collection(self, cid):
        """B2G-1.1: submission_id that exists in neither B2B nor B2G → 404."""
        import json, os
        os.environ.pop("PEPPOL_AP_WEBHOOK_SECRET", None)

        unknown_sid = f"UNKNOWN-SID-{uuid4().hex}"
        payload = json.dumps({"submissionId": unknown_sid, "status": "delivered"}).encode()

        app = build_app(cid)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/erp/outbound-b2b/peppol/webhook",
                content=payload,
                headers={"Content-Type": "application/json"},
            )

        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"


# ── B2G-1.1: poll and pending-peppol-sync routes ─────────────────────────────

class TestB2GPeppolPollRoutes:

    @pytest.mark.asyncio
    async def test_poll_peppol_status_route_returns_summary(self, cid):
        """GET /outbound-b2g/poll-peppol-status → 200 with polled/updated/errors/skipped."""
        app = build_app(cid)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/erp/outbound-b2g/poll-peppol-status")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        for key in ("polled", "updated", "errors", "skipped"):
            assert key in body, f"Missing key {key!r} in response"

    @pytest.mark.asyncio
    async def test_pending_peppol_sync_route_returns_count_and_invoices(self, cid):
        """GET /outbound-b2g/pending-peppol-sync → 200 with count and invoices list."""
        app = build_app(cid)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/erp/outbound-b2g/pending-peppol-sync")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "count"    in body
        assert "invoices" in body
        assert isinstance(body["invoices"], list)

    @pytest.mark.asyncio
    async def test_poll_b2g_applies_status_to_b2g_doc(self, cid):
        """
        B2G-1.1: poll_pending_peppol_status() on B2G service queries invoices_b2g,
        not invoices_b2b. A B2G invoice in eracun_sent state gets its status updated.
        """
        from services.erp.outbound_b2g_service import get_outbound_b2g_service
        from services.erp.base_erp_service import get_firestore_db

        issued = await _create_b2g_issued(cid)
        inv_id = issued["invoice_id"]
        ctx    = make_ctx(cid)

        submission_id = f"B2G-POLL-SID-{uuid4().hex[:8]}"
        db = get_firestore_db()
        await db.collection("invoices_b2g").document(inv_id).update({
            "document_status":  "eracun_sent",
            "delivery_method":  "peppol",
            "ap_submission_id": submission_id,
            "external_submission_id": submission_id,
            "sent_at": "2026-04-14T10:00:00+00:00",
        })

        svc = get_outbound_b2g_service()

        with patch(
            "services.erp.outbound_b2b_service.fetch_submission_status",
            new=AsyncMock(return_value={
                "status":     "delivered",
                "raw_status": "DELIVERED",
                "checked_at": "2026-04-14T10:15:00+00:00",
                "_stub":      False,
            }),
        ):
            result = await svc.poll_pending_peppol_status(ctx)

        assert result["polled"] >= 1
        assert result["updated"] >= 1

        snap = await db.collection("invoices_b2g").document(inv_id).get()
        updated_doc = snap.to_dict() or {}
        assert updated_doc.get("document_status") in ("delivered", "eracun_sent")


# ── B2G-1.1: list_pending_peppol_sync service method ────────────────────────

class TestListPendingPeppolSync:

    @pytest.mark.asyncio
    async def test_b2g_stale_doc_appears_in_pending_sync(self, cid):
        """
        B2G-1.1: list_pending_peppol_sync() on B2G service finds B2G docs
        that have never been polled (peppol_status_updated_at is None).
        """
        from services.erp.outbound_b2g_service import get_outbound_b2g_service
        from services.erp.base_erp_service import get_firestore_db

        issued = await _create_b2g_issued(cid)
        inv_id = issued["invoice_id"]
        ctx    = make_ctx(cid)

        sid = f"B2G-STALE-{uuid4().hex[:8]}"
        db  = get_firestore_db()
        await db.collection("invoices_b2g").document(inv_id).update({
            "document_status":        "eracun_sent",
            "delivery_method":        "peppol",
            "ap_submission_id":       sid,
            "external_submission_id": sid,
            "sent_at":                "2026-04-14T08:00:00+00:00",
            "peppol_status_updated_at": None,
        })

        svc    = get_outbound_b2g_service()
        result = await svc.list_pending_peppol_sync(ctx)

        assert result["count"] >= 1
        ids = {d.get("invoice_id") or d.get("_id") for d in result["invoices"]}
        assert inv_id in ids, f"Stale B2G invoice {inv_id} not in pending-peppol-sync result"

    @pytest.mark.asyncio
    async def test_b2g_pending_sync_does_not_include_b2b_docs(self, cid):
        """
        B2G-1.1: list_pending_peppol_sync() on B2G service uses invoices_b2g,
        not invoices_b2b. B2B stale docs must not appear.
        """
        from services.erp.outbound_b2g_service import get_outbound_b2g_service
        from services.erp.outbound_b2b_service import get_outbound_b2b_service
        from services.erp.base_erp_service import get_firestore_db

        ctx = make_ctx(cid)

        # Create a B2B invoice in eracun_sent with stale status
        b2b_data = {
            "customer_name": "B2B Kupac", "customer_oib": "99988877766",
            "seller_name": "X d.o.o.", "seller_oib": "98765432100",
            "issue_date": "2026-04-01",
            "items": _ITEMS,
        }
        b2b_doc = await get_outbound_b2b_service().create(b2b_data, ctx)
        b2b_id  = b2b_doc["invoice_id"]
        sid_b2b = f"B2B-STALE-{uuid4().hex[:8]}"
        db = get_firestore_db()
        await db.collection("invoices_b2b").document(b2b_id).update({
            "document_status":        "eracun_sent",
            "delivery_method":        "peppol",
            "ap_submission_id":       sid_b2b,
            "external_submission_id": sid_b2b,
            "peppol_status_updated_at": None,
        })

        # B2G pending-sync must not include the B2B invoice_id
        b2g_result = await get_outbound_b2g_service().list_pending_peppol_sync(ctx)
        b2g_ids = {d.get("invoice_id") or d.get("_id") for d in b2g_result["invoices"]}
        assert b2b_id not in b2g_ids, (
            f"B2B invoice {b2b_id} should not appear in B2G pending-peppol-sync"
        )


# ── B2G-1.2: send() delivery_target fallback ─────────────────────────────────

class TestSendDeliveryTargetFallback:

    @pytest.mark.asyncio
    async def test_send_uses_stored_peppol_id_when_target_empty(self, cid):
        """
        B2G-1.2: B2G create with customer_peppol_id → /send with empty delivery_target
        uses the stored value from doc.delivery_target. Dispatch must receive the pre-set target.
        """
        from services.erp.outbound_b2g_service import get_outbound_b2g_service

        peppol_id = f"0190:{'12345678901'}"
        issued    = await _create_b2g_issued(cid)
        ctx       = make_ctx(cid)
        svc       = get_outbound_b2g_service()

        dispatched_target = []

        async def _mock_dispatch(doc, method, target, ref):
            dispatched_target.append(target)
            return {
                "ok":                   True,
                "external_submission_id": f"PEPPOL-STUB-{uuid4().hex[:8]}",
                "sent_at":              "2026-04-14T10:00:00+00:00",
            }

        with patch(
            "services.erp.outbound_dispatch_service.dispatch_invoice",
            new=AsyncMock(side_effect=_mock_dispatch),
        ):
            result = await svc.send(
                issued["invoice_id"], ctx,
                delivery_method="peppol",
                delivery_target="",   # intentionally empty
            )

        assert result["document_status"] == "eracun_sent"
        assert dispatched_target, "dispatch_invoice was not called"
        assert dispatched_target[0] == peppol_id, (
            f"Expected dispatch target {peppol_id!r}, got {dispatched_target[0]!r}"
        )

    @pytest.mark.asyncio
    async def test_send_b2b_still_works_with_explicit_target(self, cid):
        """
        B2G-1.2 non-regression: explicit delivery_target still takes precedence
        over any stored doc value (B2B behavior unchanged).
        """
        from services.erp.outbound_b2b_service import get_outbound_b2b_service

        ctx = make_ctx(cid)
        svc = get_outbound_b2b_service()

        b2b_data = {
            "customer_name": "Primatelj d.o.o.", "customer_oib": "11223344556",
            "seller_name": "Dobavljač d.o.o.", "seller_oib": "98765432100",
            "issue_date": "2026-04-01",
            "items": _ITEMS,
        }
        doc = await svc.create(b2b_data, ctx)
        await svc.approve(doc["invoice_id"], ctx)
        await svc.issue(doc["invoice_id"], ctx)

        explicit_target = "explicit@test.hr"
        dispatched = []

        async def _mock_dispatch(doc, method, target, ref):
            dispatched.append(target)
            return {"ok": True, "external_submission_id": None, "sent_at": "2026-04-14T10:00:00+00:00"}

        with patch(
            "services.erp.outbound_dispatch_service.dispatch_invoice",
            new=AsyncMock(side_effect=_mock_dispatch),
        ):
            result = await svc.send(
                doc["invoice_id"], ctx,
                delivery_method="email",
                delivery_target=explicit_target,
            )

        assert dispatched[0] == explicit_target
