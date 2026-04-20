"""
Sprint C2.2.1 — API regression tests for Peppol feedback routes
================================================================
Tests three routes added in C2.2 / C2.2.1:

  POST /api/erp/outbound-b2b/peppol/webhook        (system-to-system, no ERP auth)
  POST /api/erp/outbound-b2b/poll-peppol-status    (operator/scheduler, ERP auth)
  GET  /api/erp/outbound-b2b/pending-peppol-sync   (operator/dashboard, ERP auth)

Key acceptance criteria:
  - Webhook accepts valid HMAC, rejects invalid; resolves company from submission_id
  - Webhook transitions SM without ERP user identity
  - poll-peppol-status triggers fetch and returns summary
  - pending-peppol-sync excludes PEPPOL-STUB-* docs
"""

import hashlib
import hmac
import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import date

from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from services.erp.errors import BusinessError
from services.erp.request_context import ERPRequestContext
from web.erp_routes import router as erp_router, get_erp_ctx

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


# ── App helpers ───────────────────────────────────────────────────────────────

def _make_app(company_id: str) -> FastAPI:
    app = FastAPI()

    @app.exception_handler(BusinessError)
    async def _biz(request: Request, exc: BusinessError):
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message},
        )

    app.include_router(erp_router)
    app.dependency_overrides[get_erp_ctx] = lambda: ERPRequestContext(
        user_id="test-user",
        company_id=company_id,
        role="owner",
        grants=["*"],
        denies=[],
        request_id=str(uuid4()),
    )
    return app


@pytest.fixture
def cid():
    return f"test_proutes_{uuid4().hex}"


@pytest_asyncio.fixture
async def sent_peppol_invoice(cid):
    """Create an issued B2B invoice with a real (non-stub) Peppol submission_id."""
    from services.erp.outbound_b2b_service import OutboundB2BService
    from services.erp.company_service import CompanyService
    from services.erp.base_erp_service import get_firestore_db

    ctx = ERPRequestContext(
        user_id="fixture-user", company_id=cid, role="owner",
        grants=["*"], denies=[], request_id=str(uuid4()),
    )
    await CompanyService().upsert({"oib": "47034854402", "name": "Route Test Firma"}, ctx)

    svc = OutboundB2BService()
    inv = await svc.create({
        "customer_name": "Ruta Kupac d.o.o.",
        "customer_oib":  "22222222220",
        "issue_date":    str(date.today()),
        "items": [{"name": "X", "description": "X", "quantity": 1,
                   "unit": "kom", "unit_price": 100.0, "vat_rate": 25}],
    }, ctx)
    await svc.approve(inv["invoice_id"], ctx)
    await svc.issue(inv["invoice_id"], ctx)

    sid = f"ROUTE-SID-{uuid4().hex[:8]}"
    await get_firestore_db().collection("invoices_b2b").document(inv["invoice_id"]).update({
        "external_submission_id": sid,
        "delivery_method":        "peppol",
        "document_status":        "eracun_sent",
        "sent_at":                str(date.today()),
        "external_status":        "pending",
    })
    return {"invoice_id": inv["invoice_id"], "submission_id": sid, "company_id": cid}


# ── POST /outbound-b2b/peppol/webhook ─────────────────────────────────────────

class TestPeppolWebhookRoute:

    @pytest.mark.asyncio
    async def test_valid_payload_transitions_doc(self, sent_peppol_invoice):
        """Valid webhook payload transitions doc eracun_sent → delivered."""
        cid  = sent_peppol_invoice["company_id"]
        sid  = sent_peppol_invoice["submission_id"]
        app  = _make_app(cid)

        payload = json.dumps({"submissionId": sid, "status": "delivered"}).encode()

        import os
        os.environ.pop("PEPPOL_AP_WEBHOOK_SECRET", None)   # no secret → accept all

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/erp/outbound-b2b/peppol/webhook",
                content=payload,
                headers={"Content-Type": "application/json"},
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True
        assert body["new_status"] == "delivered"

    @pytest.mark.asyncio
    async def test_webhook_needs_no_erp_user_headers(self, sent_peppol_invoice):
        """Webhook must work without X-ERP-User-Id / X-ERP-Company-Id headers."""
        sid = sent_peppol_invoice["submission_id"]
        app = _make_app(sent_peppol_invoice["company_id"])

        # Build a fresh app WITHOUT the dependency override so no ERP auth is injected
        bare_app = FastAPI()
        bare_app.exception_handler(BusinessError)(
            lambda req, exc: JSONResponse(
                status_code=exc.http_status,
                content={"code": exc.code, "message": exc.message},
            )
        )
        bare_app.include_router(erp_router)
        # Do NOT add dependency_overrides — simulate a real AP call

        payload = json.dumps({"submissionId": sid, "status": "pending"}).encode()

        import os
        os.environ.pop("PEPPOL_AP_WEBHOOK_SECRET", None)

        async with AsyncClient(transport=ASGITransport(app=bare_app), base_url="http://test") as client:
            resp = await client.post(
                "/api/erp/outbound-b2b/peppol/webhook",
                content=payload,
                headers={"Content-Type": "application/json"},
            )

        # Should succeed (200) with no user headers — not 401/403
        assert resp.status_code == 200, (
            f"Webhook must not require ERP user headers. Got {resp.status_code}: {resp.text}"
        )

    @pytest.mark.asyncio
    async def test_webhook_invalid_hmac_returns_403(self, sent_peppol_invoice):
        """When PEPPOL_AP_WEBHOOK_SECRET is set, wrong signature → 403."""
        sid = sent_peppol_invoice["submission_id"]
        bare_app = FastAPI()
        bare_app.include_router(erp_router)

        payload = json.dumps({"submissionId": sid, "status": "delivered"}).encode()

        with patch.dict("os.environ", {"PEPPOL_AP_WEBHOOK_SECRET": "real-secret"}):
            async with AsyncClient(transport=ASGITransport(app=bare_app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/erp/outbound-b2b/peppol/webhook",
                    content=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-Peppol-Signature": "badhex",
                    },
                )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_webhook_valid_hmac_accepted(self, sent_peppol_invoice):
        """Valid HMAC signature is accepted even when secret is set."""
        sid     = sent_peppol_invoice["submission_id"]
        secret  = "webhook-test-secret-abc"
        payload = json.dumps({"submissionId": sid, "status": "pending"}).encode()
        sig     = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        bare_app = FastAPI()
        bare_app.include_router(erp_router)

        with patch.dict("os.environ", {"PEPPOL_AP_WEBHOOK_SECRET": secret}):
            async with AsyncClient(transport=ASGITransport(app=bare_app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/erp/outbound-b2b/peppol/webhook",
                    content=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-Peppol-Signature": sig,
                    },
                )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_webhook_missing_submission_id_returns_400(self, cid):
        """Payload without submissionId → 400."""
        app = _make_app(cid)
        payload = json.dumps({"status": "delivered"}).encode()

        import os
        os.environ.pop("PEPPOL_AP_WEBHOOK_SECRET", None)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/erp/outbound-b2b/peppol/webhook",
                content=payload,
                headers={"Content-Type": "application/json"},
            )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_webhook_rejected_transitions_to_rejected(self, cid):
        """Webhook 'rejected' status transitions doc to rejected SM state."""
        from services.erp.outbound_b2b_service import OutboundB2BService
        from services.erp.company_service import CompanyService
        from services.erp.base_erp_service import get_firestore_db

        ctx = ERPRequestContext(
            user_id="t", company_id=cid, role="owner",
            grants=["*"], denies=[], request_id=str(uuid4()),
        )
        await CompanyService().upsert({"oib": "47034854402", "name": "T"}, ctx)

        svc = OutboundB2BService()
        inv = await svc.create({
            "customer_name": "K d.o.o.", "customer_oib": "33333333330",
            "issue_date": str(date.today()),
            "items": [{"name": "X", "description": "X", "quantity": 1,
                       "unit": "kom", "unit_price": 10.0, "vat_rate": 25}],
        }, ctx)
        await svc.approve(inv["invoice_id"], ctx)
        await svc.issue(inv["invoice_id"], ctx)

        sid = f"REJ-SID-{uuid4().hex[:8]}"
        await get_firestore_db().collection("invoices_b2b").document(inv["invoice_id"]).update({
            "external_submission_id": sid,
            "delivery_method": "peppol",
            "document_status": "eracun_sent",
            "sent_at": str(date.today()),
            "external_status": "pending",
        })

        app = _make_app(cid)
        payload = json.dumps({
            "submissionId": sid,
            "status": "rejected",
            "rejectionReason": "Neispravan PDV broj",
        }).encode()

        import os
        os.environ.pop("PEPPOL_AP_WEBHOOK_SECRET", None)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/erp/outbound-b2b/peppol/webhook",
                content=payload,
                headers={"Content-Type": "application/json"},
            )

        assert resp.status_code == 200
        assert resp.json()["new_status"] == "rejected"


# ── POST /outbound-b2b/poll-peppol-status ─────────────────────────────────────

class TestPollPeppolStatusRoute:

    @pytest.mark.asyncio
    async def test_poll_returns_summary(self, cid):
        """Route returns the poll summary dict."""
        app = _make_app(cid)
        import os
        os.environ.pop("PEPPOL_AP_ENDPOINT", None)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/erp/outbound-b2b/poll-peppol-status")

        assert resp.status_code == 200
        body = resp.json()
        assert "polled"  in body
        assert "updated" in body
        assert "errors"  in body
        assert "skipped" in body

    @pytest.mark.asyncio
    async def test_poll_updates_doc_when_ap_returns_delivered(self, cid):
        """poll-peppol-status route triggers SM transition via mocked AP."""
        from services.erp.outbound_b2b_service import OutboundB2BService
        from services.erp.company_service import CompanyService
        from services.erp.base_erp_service import get_firestore_db

        ctx = ERPRequestContext(
            user_id="t", company_id=cid, role="owner",
            grants=["*"], denies=[], request_id=str(uuid4()),
        )
        await CompanyService().upsert({"oib": "47034854402", "name": "T"}, ctx)

        svc = OutboundB2BService()
        inv = await svc.create({
            "customer_name": "K d.o.o.", "customer_oib": "44444444440",
            "issue_date": str(date.today()),
            "items": [{"name": "X", "description": "X", "quantity": 1,
                       "unit": "kom", "unit_price": 10.0, "vat_rate": 25}],
        }, ctx)
        await svc.approve(inv["invoice_id"], ctx)
        await svc.issue(inv["invoice_id"], ctx)

        sid = f"POLL-ROUTE-SID-{uuid4().hex[:8]}"
        db  = get_firestore_db()
        await db.collection("invoices_b2b").document(inv["invoice_id"]).update({
            "external_submission_id": sid,
            "delivery_method": "peppol",
            "document_status": "eracun_sent",
            "sent_at": str(date.today()),
            "external_status": "pending",
        })

        mock_status = {
            "submission_id": sid, "raw_status": "delivered",
            "status": "delivered", "is_terminal": False,
            "checked_at": "2026-04-11T12:00:00+00:00",
        }

        app = _make_app(cid)
        with patch.dict("os.environ", {"PEPPOL_AP_ENDPOINT": "https://ap.test"}):
            with patch(
                "services.erp.outbound_b2b_service.fetch_submission_status",
                new=AsyncMock(return_value=mock_status),
            ):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    resp = await client.post("/api/erp/outbound-b2b/poll-peppol-status")

        assert resp.status_code == 200
        body = resp.json()
        assert body["updated"] >= 1

        snap = await db.collection("invoices_b2b").document(inv["invoice_id"]).get()
        assert (snap.to_dict() or {})["document_status"] == "delivered"


# ── GET /outbound-b2b/pending-peppol-sync ─────────────────────────────────────

class TestPendingPeppolSyncRoute:

    @pytest.mark.asyncio
    async def test_stub_docs_excluded(self, cid):
        """PEPPOL-STUB-* submission IDs must not appear in pending-peppol-sync."""
        from services.erp.outbound_b2b_service import OutboundB2BService
        from services.erp.company_service import CompanyService
        from services.erp.base_erp_service import get_firestore_db

        ctx = ERPRequestContext(
            user_id="t", company_id=cid, role="owner",
            grants=["*"], denies=[], request_id=str(uuid4()),
        )
        await CompanyService().upsert({"oib": "47034854402", "name": "T"}, ctx)

        svc = OutboundB2BService()
        inv = await svc.create({
            "customer_name": "K d.o.o.", "customer_oib": "55555555550",
            "issue_date": str(date.today()),
            "items": [{"name": "X", "description": "X", "quantity": 1,
                       "unit": "kom", "unit_price": 10.0, "vat_rate": 25}],
        }, ctx)
        await svc.approve(inv["invoice_id"], ctx)
        await svc.issue(inv["invoice_id"], ctx)

        stub_sid = "PEPPOL-STUB-TESTABCDEF12"
        await get_firestore_db().collection("invoices_b2b").document(inv["invoice_id"]).update({
            "external_submission_id": stub_sid,
            "delivery_method": "peppol",
            "document_status": "eracun_sent",
            "sent_at": str(date.today()),
            "external_status": "pending",
            # No peppol_status_updated_at → would appear if not filtered
        })

        app = _make_app(cid)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/erp/outbound-b2b/pending-peppol-sync")

        assert resp.status_code == 200
        body = resp.json()
        sids = [d.get("external_submission_id") for d in body["invoices"]]
        assert stub_sid not in sids, (
            f"PEPPOL-STUB-* docs must be excluded from pending-peppol-sync. Found: {sids}"
        )

    @pytest.mark.asyncio
    async def test_real_sid_without_check_appears(self, cid):
        """A real (non-stub) Peppol invoice never checked must appear in the list."""
        from services.erp.outbound_b2b_service import OutboundB2BService
        from services.erp.company_service import CompanyService
        from services.erp.base_erp_service import get_firestore_db

        ctx = ERPRequestContext(
            user_id="t", company_id=cid, role="owner",
            grants=["*"], denies=[], request_id=str(uuid4()),
        )
        await CompanyService().upsert({"oib": "47034854402", "name": "T"}, ctx)

        svc = OutboundB2BService()
        inv = await svc.create({
            "customer_name": "K d.o.o.", "customer_oib": "66666666660",
            "issue_date": str(date.today()),
            "items": [{"name": "X", "description": "X", "quantity": 1,
                       "unit": "kom", "unit_price": 10.0, "vat_rate": 25}],
        }, ctx)
        await svc.approve(inv["invoice_id"], ctx)
        await svc.issue(inv["invoice_id"], ctx)

        real_sid = f"REAL-PENDING-{uuid4().hex[:8]}"
        await get_firestore_db().collection("invoices_b2b").document(inv["invoice_id"]).update({
            "external_submission_id": real_sid,
            "delivery_method": "peppol",
            "document_status": "eracun_sent",
            "sent_at": str(date.today()),
            "external_status": "pending",
            # No peppol_status_updated_at → should appear
        })

        app = _make_app(cid)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/erp/outbound-b2b/pending-peppol-sync")

        assert resp.status_code == 200
        body = resp.json()
        sids = [d.get("external_submission_id") for d in body["invoices"]]
        assert real_sid in sids, (
            f"Real Peppol invoice without status check must appear in pending-peppol-sync. Got: {sids}"
        )
        assert body["count"] >= 1
