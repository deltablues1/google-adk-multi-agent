"""
Sprint C2.2.2 — Peppol submission ID hardening tests
======================================================
Locks the behaviour when AP submission IDs collide or are recycled.

Scenarios covered:
  - Duplicate submission_id in same company → guard at send() suffixes the ID
  - Two docs with same submission_id (recycled) → global lookup disambiguates
    via receiver_participant_id hint
  - Two docs with same submission_id, no hint → first found is used, warning logged
  - Webhook payload with receiver/sender fields → hints reach global lookup
"""

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from uuid import uuid4
from datetime import date

from services.erp.request_context import ERPRequestContext

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


def make_ctx(company_id: str) -> ERPRequestContext:
    return ERPRequestContext(
        user_id="test-c222",
        company_id=company_id,
        role="owner",
        grants=["*"],
        denies=[],
        request_id=str(uuid4()),
    )


@pytest.fixture
def cid():
    return f"test_c222_{uuid4().hex}"


async def _create_issued(company_id: str, customer_oib: str) -> dict:
    """Create an approved+issued B2B invoice. Returns doc dict."""
    from services.erp.outbound_b2b_service import OutboundB2BService
    from services.erp.company_service import CompanyService

    ctx = make_ctx(company_id)
    await CompanyService().upsert({"oib": "47034854402", "name": "Hard Test Firma"}, ctx)
    svc = OutboundB2BService()
    inv = await svc.create({
        "customer_name": "K d.o.o.",
        "customer_oib":  customer_oib,
        "issue_date":    str(date.today()),
        "items": [{"name": "X", "description": "X", "quantity": 1,
                   "unit": "kom", "unit_price": 100.0, "vat_rate": 25}],
    }, ctx)
    await svc.approve(inv["invoice_id"], ctx)
    await svc.issue(inv["invoice_id"], ctx)
    return inv


# ── Guard at send() — duplicate submission_id in same company ─────────────────

class TestSubmissionIdConflictGuard:

    @pytest.mark.asyncio
    async def test_duplicate_sid_gets_suffixed(self, cid):
        """
        When send() returns a submission_id already assigned to another doc
        in the same company, the new doc gets a suffixed ID (not silent collision).
        """
        from services.erp.outbound_b2b_service import OutboundB2BService
        from services.erp.base_erp_service import get_firestore_db

        ctx = make_ctx(cid)
        svc = OutboundB2BService()

        # First invoice — already has a known real submission ID
        inv1 = await _create_issued(cid, "11111111110")
        recycled_sid = f"RECYCLED-SID-{uuid4().hex[:8]}"
        await get_firestore_db().collection("invoices_b2b").document(inv1["invoice_id"]).update({
            "external_submission_id": recycled_sid,
            "delivery_method":        "peppol",
            "document_status":        "eracun_sent",
            "sent_at":                str(date.today()),
            "external_status":        "pending",
        })

        # Second invoice — send() returns the same submission_id from AP
        inv2 = await _create_issued(cid, "22222222220")
        inv2_id = inv2["invoice_id"]

        mock_dispatch_result = {
            "ok":                    True,
            "external_submission_id": recycled_sid,   # AP recycled the ID
            "sent_at":               "2026-04-11T10:00:00+00:00",
            "method":                "peppol",
        }

        with patch(
            "services.erp.outbound_dispatch_service.dispatch_invoice",
            new=AsyncMock(return_value=mock_dispatch_result),
        ):
            result = await svc.send(
                inv2_id, ctx, "peppol", "0190:22222222220"
            )

        stored_sid = result.get("external_submission_id") or ""
        assert stored_sid != recycled_sid, (
            "When submission_id collides with existing doc, it must be suffixed"
        )
        assert recycled_sid in stored_sid, (
            "Suffixed ID must still contain the original submission_id for AP cross-reference"
        )
        assert inv2_id[:8] in stored_sid, (
            "Suffix must include invoice_id fragment for traceability"
        )

    @pytest.mark.asyncio
    async def test_no_collision_stores_original_sid(self, cid):
        """When submission_id is unique, it is stored as-is without suffix."""
        from services.erp.outbound_b2b_service import OutboundB2BService

        ctx  = make_ctx(cid)
        svc  = OutboundB2BService()
        inv  = await _create_issued(cid, "33333333330")
        sid  = f"UNIQUE-SID-{uuid4().hex[:8]}"

        mock_dispatch_result = {
            "ok": True, "external_submission_id": sid,
            "sent_at": "2026-04-11T10:00:00+00:00", "method": "peppol",
        }

        with patch(
            "services.erp.outbound_dispatch_service.dispatch_invoice",
            new=AsyncMock(return_value=mock_dispatch_result),
        ):
            result = await svc.send(inv["invoice_id"], ctx, "peppol", "0190:33333333330")

        assert result["external_submission_id"] == sid, (
            "Unique submission_id must be stored verbatim"
        )

    @pytest.mark.asyncio
    async def test_stub_ids_not_checked_for_collision(self, cid):
        """PEPPOL-STUB-* IDs bypass the collision guard — stubs are never unique."""
        from services.erp.outbound_b2b_service import OutboundB2BService
        from services.erp.base_erp_service import get_firestore_db

        ctx  = make_ctx(cid)
        svc  = OutboundB2BService()

        # First doc with a stub ID
        inv1 = await _create_issued(cid, "44444444440")
        stub_sid = "PEPPOL-STUB-AABBCCDDEE11"
        await get_firestore_db().collection("invoices_b2b").document(inv1["invoice_id"]).update({
            "external_submission_id": stub_sid,
            "delivery_method":        "peppol",
            "document_status":        "eracun_sent",
            "sent_at":                str(date.today()),
            "external_status":        "pending",
        })

        # Second invoice — AP also returns same stub-looking ID (unlikely but valid)
        inv2 = await _create_issued(cid, "55555555550")
        mock_dispatch_result = {
            "ok": True, "external_submission_id": stub_sid,
            "sent_at": "2026-04-11T10:00:00+00:00", "method": "peppol",
            "_stub": True,
        }

        with patch(
            "services.erp.outbound_dispatch_service.dispatch_invoice",
            new=AsyncMock(return_value=mock_dispatch_result),
        ):
            result = await svc.send(inv2["invoice_id"], ctx, "peppol", "0190:55555555550")

        # Stub IDs are exempt from collision guard — stored as-is
        assert result["external_submission_id"] == stub_sid


# ── Global lookup disambiguation ─────────────────────────────────────────────

class TestGlobalLookupDisambiguation:

    @pytest_asyncio.fixture
    async def two_docs_same_sid(self, cid):
        """Two invoices in the same company sharing a submission_id (recycled by AP)."""
        from services.erp.outbound_b2b_service import OutboundB2BService
        from services.erp.base_erp_service import get_firestore_db
        from services.erp.company_service import CompanyService

        ctx = make_ctx(cid)
        await CompanyService().upsert({"oib": "47034854402", "name": "T"}, ctx)
        svc = OutboundB2BService()
        recycled_sid = f"RECYCLE-{uuid4().hex[:10]}"

        inv_a = await svc.create({
            "customer_name": "Kupac A", "customer_oib": "66666666660",
            "issue_date": str(date.today()),
            "items": [{"name": "A", "description": "A", "quantity": 1,
                       "unit": "kom", "unit_price": 10.0, "vat_rate": 25}],
        }, ctx)
        await svc.approve(inv_a["invoice_id"], ctx)
        await svc.issue(inv_a["invoice_id"], ctx)
        await get_firestore_db().collection("invoices_b2b").document(inv_a["invoice_id"]).update({
            "external_submission_id": recycled_sid,
            "delivery_method": "peppol",
            "document_status": "eracun_sent",
            "delivery_target": "0190:66666666660",
            "external_status": "pending",
        })

        inv_b = await svc.create({
            "customer_name": "Kupac B", "customer_oib": "77777777770",
            "issue_date": str(date.today()),
            "items": [{"name": "B", "description": "B", "quantity": 1,
                       "unit": "kom", "unit_price": 10.0, "vat_rate": 25}],
        }, ctx)
        await svc.approve(inv_b["invoice_id"], ctx)
        await svc.issue(inv_b["invoice_id"], ctx)
        await get_firestore_db().collection("invoices_b2b").document(inv_b["invoice_id"]).update({
            "external_submission_id": recycled_sid,
            "delivery_method": "peppol",
            "document_status": "eracun_sent",
            "delivery_target": "0190:77777777770",
            "external_status": "pending",
        })

        return {
            "inv_a": inv_a["invoice_id"],
            "inv_b": inv_b["invoice_id"],
            "sid":   recycled_sid,
            "svc":   svc,
        }

    @pytest.mark.asyncio
    async def test_receiver_hint_picks_correct_doc(self, two_docs_same_sid):
        """When AP provides receiver hint, correct doc is selected."""
        data = two_docs_same_sid
        doc = await data["svc"].get_by_submission_id_global(
            data["sid"],
            receiver_participant_id="0190:77777777770",   # points to inv_b
        )
        assert doc["invoice_id"] == data["inv_b"], (
            "Receiver participant hint must select the matching delivery_target doc"
        )

    @pytest.mark.asyncio
    async def test_no_hint_returns_first_found_without_crash(self, two_docs_same_sid):
        """Without hints, global lookup returns a doc (first found) and does not crash."""
        data = two_docs_same_sid
        # Should not raise — logs warning and returns something
        doc = await data["svc"].get_by_submission_id_global(data["sid"])
        assert doc["invoice_id"] in (data["inv_a"], data["inv_b"]), (
            "Without hints, a doc must still be returned (first found)"
        )

    @pytest.mark.asyncio
    async def test_webhook_with_receiver_hint_routes_correctly(self, two_docs_same_sid, cid):
        """
        Webhook payload containing receiverId disambiguates and transitions the right doc.
        """
        import json
        from httpx import AsyncClient, ASGITransport
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse
        from services.erp.errors import BusinessError
        from web.erp_routes import router as erp_router

        data = two_docs_same_sid

        app = FastAPI()
        app.exception_handler(BusinessError)(
            lambda req, exc: JSONResponse(
                status_code=exc.http_status,
                content={"code": exc.code, "message": exc.message},
            )
        )
        app.include_router(erp_router)

        payload = json.dumps({
            "submissionId": data["sid"],
            "status":       "delivered",
            "receiverId":   "0190:77777777770",   # points to inv_b
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
        body = resp.json()
        assert body["invoice_id"] == data["inv_b"], (
            "Webhook with receiverId hint must transition inv_b, not inv_a"
        )
        assert body["new_status"] == "delivered"


# ── C2.2.3.1 — resend() two-field model regression ───────────────────────────

class TestResendTwoFieldModel:

    @pytest.mark.asyncio
    async def test_resend_unique_sid_stores_all_three_fields(self, cid):
        """resend() with a unique AP ID stores ap_submission_id, external_submission_key,
        and external_submission_id — all equal when no collision."""
        from services.erp.outbound_b2b_service import OutboundB2BService

        ctx = make_ctx(cid)
        svc = OutboundB2BService()
        inv = await _create_issued(cid, "88888888880")
        sid = f"RESEND-UNIQUE-{uuid4().hex[:8]}"

        mock_result = {
            "ok": True, "external_submission_id": sid,
            "sent_at": "2026-04-13T10:00:00+00:00", "method": "peppol",
        }
        with patch(
            "services.erp.outbound_dispatch_service.dispatch_invoice",
            new=AsyncMock(return_value=mock_result),
        ):
            result = await svc.resend(inv["invoice_id"], ctx, "peppol", "0190:88888888880")

        assert result["ap_submission_id"]        == sid
        assert result["external_submission_key"] == sid
        assert result["external_submission_id"]  == sid

    @pytest.mark.asyncio
    async def test_resend_collided_sid_gets_suffixed(self, cid):
        """resend() with a recycled AP ID suffixes external_submission_key
        but keeps ap_submission_id verbatim."""
        from services.erp.outbound_b2b_service import OutboundB2BService
        from services.erp.base_erp_service import get_firestore_db

        ctx = make_ctx(cid)
        svc = OutboundB2BService()

        # First invoice already has the SID recorded in external_submission_id (legacy field)
        inv1 = await _create_issued(cid, "99999999990")
        recycled_sid = f"RESEND-RECYCLED-{uuid4().hex[:8]}"
        await get_firestore_db().collection("invoices_b2b").document(inv1["invoice_id"]).update({
            "external_submission_id": recycled_sid,
            "delivery_method":        "peppol",
            "document_status":        "eracun_sent",
            "sent_at":                str(date.today()),
            "external_status":        "pending",
        })

        # Second invoice — resend() gets the same SID back from AP
        inv2 = await _create_issued(cid, "10000000000")
        inv2_id = inv2["invoice_id"]

        mock_result = {
            "ok": True, "external_submission_id": recycled_sid,
            "sent_at": "2026-04-13T10:00:00+00:00", "method": "peppol",
        }
        with patch(
            "services.erp.outbound_dispatch_service.dispatch_invoice",
            new=AsyncMock(return_value=mock_result),
        ):
            result = await svc.resend(inv2_id, ctx, "peppol", "0190:10000000000")

        assert result["ap_submission_id"] == recycled_sid, (
            "ap_submission_id must be verbatim even on collision"
        )
        assert result["external_submission_id"] != recycled_sid, (
            "external_submission_id must be suffixed on collision"
        )
        assert recycled_sid in result["external_submission_id"], (
            "Suffixed key must still contain original AP SID"
        )
        assert inv2_id[:8] in result["external_submission_id"], (
            "Suffix must include invoice_id fragment for traceability"
        )

    @pytest.mark.asyncio
    async def test_resend_stub_sid_not_collision_checked(self, cid):
        """resend() with PEPPOL-STUB-* ID bypasses collision guard."""
        from services.erp.outbound_b2b_service import OutboundB2BService
        from services.erp.base_erp_service import get_firestore_db

        ctx = make_ctx(cid)
        svc = OutboundB2BService()

        stub_sid = "PEPPOL-STUB-RESEND112233"

        # First doc already has the stub SID
        inv1 = await _create_issued(cid, "20000000000")
        await get_firestore_db().collection("invoices_b2b").document(inv1["invoice_id"]).update({
            "external_submission_id": stub_sid,
            "delivery_method":        "peppol",
            "document_status":        "eracun_sent",
            "sent_at":                str(date.today()),
            "external_status":        "pending",
        })

        # Second invoice resends with the same stub SID
        inv2 = await _create_issued(cid, "30000000000")
        mock_result = {
            "ok": True, "external_submission_id": stub_sid,
            "sent_at": "2026-04-13T10:00:00+00:00", "method": "peppol",
            "_stub": True,
        }
        with patch(
            "services.erp.outbound_dispatch_service.dispatch_invoice",
            new=AsyncMock(return_value=mock_result),
        ):
            result = await svc.resend(inv2["invoice_id"], ctx, "peppol", "0190:30000000000")

        # Stub IDs bypass collision guard — stored verbatim in all three fields
        assert result["ap_submission_id"]       == stub_sid
        assert result["external_submission_id"] == stub_sid
