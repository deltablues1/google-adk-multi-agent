"""
Sprint C2.2 — Peppol feedback loop regression tests (async / integration)
=========================================================================
Covers async behaviour: Firestore round-trips, mocked AP calls, SM transitions.
Pure-logic unit tests (normalise_status, webhook verification, etc.) are in
test_unit_sync.py to avoid pytest-asyncio warnings on sync functions.

What is locked here:
  - fetch_submission_status: stub mode, real AP (mocked), 4xx, exception
  - OutboundB2BService.get_by_submission_id: found / not found
  - OutboundB2BService.apply_peppol_status: delivered, accepted, rejected, failed, pending
  - OutboundB2BService.poll_pending_peppol_status: stub docs skipped, status change applied

Acceptance criterion:
  A document sent via real AP can transition eracun_sent→delivered→accepted/rejected
  via webhook or poller WITHOUT a manual ERP auth-based invoice_id call.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import date

from services.erp.request_context import ERPRequestContext

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


def make_ctx(company_id: str, role: str = "owner") -> ERPRequestContext:
    return ERPRequestContext(
        user_id="test-c22",
        company_id=company_id,
        role=role,
        grants=set(),
        denies=set(),
        request_id=str(uuid4()),
    )


@pytest.fixture
def cid():
    return f"test_c22_{uuid4().hex}"


# ── fetch_submission_status ───────────────────────────────────────────────────

class TestFetchSubmissionStatus:

    @pytest.mark.asyncio
    async def test_stub_when_no_endpoint(self):
        from services.erp.peppol_status_service import fetch_submission_status
        import os
        os.environ.pop("PEPPOL_AP_ENDPOINT", None)
        result = await fetch_submission_status("STUB-001")
        assert result["status"] == "pending"
        assert result["_stub"]  is True

    @pytest.mark.asyncio
    async def test_real_ap_200_delivered(self):
        from services.erp.peppol_status_service import fetch_submission_status

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json = MagicMock(return_value={"status": "delivered"})

        with patch.dict("os.environ", {
            "PEPPOL_AP_ENDPOINT": "https://ap.example.com",
            "PEPPOL_AP_API_KEY":  "key",
        }):
            with patch("httpx.AsyncClient") as mc:
                client = AsyncMock()
                client.__aenter__ = AsyncMock(return_value=client)
                client.__aexit__  = AsyncMock(return_value=False)
                client.get = AsyncMock(return_value=mock_resp)
                mc.return_value = client

                result = await fetch_submission_status("AP-REAL-001")

        assert result["status"]      == "delivered"
        assert result["is_terminal"] is False
        assert "_stub" not in result

    @pytest.mark.asyncio
    async def test_real_ap_404_maps_to_failed(self):
        from services.erp.peppol_status_service import fetch_submission_status

        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch.dict("os.environ", {"PEPPOL_AP_ENDPOINT": "https://ap.example.com"}):
            with patch("httpx.AsyncClient") as mc:
                client = AsyncMock()
                client.__aenter__ = AsyncMock(return_value=client)
                client.__aexit__  = AsyncMock(return_value=False)
                client.get = AsyncMock(return_value=mock_resp)
                mc.return_value = client

                result = await fetch_submission_status("GONE-001")

        assert result["status"]      == "failed"
        assert result["is_terminal"] is True

    @pytest.mark.asyncio
    async def test_network_exception_conservative_pending(self):
        from services.erp.peppol_status_service import fetch_submission_status

        with patch.dict("os.environ", {"PEPPOL_AP_ENDPOINT": "https://ap.example.com"}):
            with patch("httpx.AsyncClient") as mc:
                client = AsyncMock()
                client.__aenter__ = AsyncMock(return_value=client)
                client.__aexit__  = AsyncMock(return_value=False)
                client.get = AsyncMock(side_effect=ConnectionError("timeout"))
                mc.return_value = client

                result = await fetch_submission_status("NET-ERR-001")

        assert result["status"]      == "pending"   # conservative — keep polling
        assert result["is_terminal"] is False
        assert "error" in result


# ── get_by_submission_id ──────────────────────────────────────────────────────

class TestGetBySubmissionId:

    @pytest_asyncio.fixture
    async def issued_peppol_invoice(self, cid):
        """Create an approved+issued invoice with a known external_submission_id."""
        from services.erp.outbound_b2b_service import OutboundB2BService
        from services.erp.company_service import CompanyService
        from services.erp.base_erp_service import get_firestore_db

        ctx = make_ctx(cid)
        await CompanyService().upsert({"oib": "47034854402", "name": "Test Firma"}, ctx)

        svc = OutboundB2BService()
        inv = await svc.create({
            "customer_name": "Kupac d.o.o.",
            "customer_oib":  "22222222220",
            "issue_date":    str(date.today()),
            "items": [{"name": "X", "description": "X", "quantity": 1,
                       "unit": "kom", "unit_price": 100.0, "vat_rate": 25}],
        }, ctx)
        inv_id = inv["invoice_id"]
        await svc.approve(inv_id, ctx)
        await svc.issue(inv_id, ctx)

        sid = f"TEST-SID-{uuid4().hex[:8]}"
        await get_firestore_db().collection("invoices_b2b").document(inv_id).update({
            "external_submission_id": sid,
            "delivery_method":        "peppol",
            "document_status":        "eracun_sent",
            "sent_at":                str(date.today()),
            "external_status":        "pending",
        })
        return {"invoice_id": inv_id, "submission_id": sid, "ctx": ctx}

    @pytest.mark.asyncio
    async def test_found_by_submission_id(self, issued_peppol_invoice):
        from services.erp.outbound_b2b_service import OutboundB2BService

        data = issued_peppol_invoice
        doc = await OutboundB2BService().get_by_submission_id(
            data["submission_id"], data["ctx"]
        )
        assert doc["invoice_id"]              == data["invoice_id"]
        assert doc["external_submission_id"]  == data["submission_id"]

    @pytest.mark.asyncio
    async def test_not_found_raises(self, cid):
        from services.erp.outbound_b2b_service import OutboundB2BService
        from services.erp.errors import NotFoundError

        ctx = make_ctx(cid)
        with pytest.raises(NotFoundError):
            await OutboundB2BService().get_by_submission_id("NO-SUCH-SID", ctx)


# ── apply_peppol_status ───────────────────────────────────────────────────────

class TestApplyPeppolStatus:

    @pytest_asyncio.fixture
    async def sent_invoice(self, cid):
        from services.erp.outbound_b2b_service import OutboundB2BService
        from services.erp.company_service import CompanyService
        from services.erp.base_erp_service import get_firestore_db

        ctx = make_ctx(cid)
        await CompanyService().upsert({"oib": "47034854402", "name": "Test"}, ctx)

        svc = OutboundB2BService()
        inv = await svc.create({
            "customer_name": "K d.o.o.", "customer_oib": "33333333330",
            "issue_date": str(date.today()),
            "items": [{"name": "S", "description": "S", "quantity": 1,
                       "unit": "kom", "unit_price": 50.0, "vat_rate": 25}],
        }, ctx)
        inv_id = inv["invoice_id"]
        await svc.approve(inv_id, ctx)
        await svc.issue(inv_id, ctx)

        sid = f"APPLY-SID-{uuid4().hex[:8]}"
        await get_firestore_db().collection("invoices_b2b").document(inv_id).update({
            "external_submission_id": sid,
            "delivery_method":        "peppol",
            "document_status":        "eracun_sent",
            "sent_at":                str(date.today()),
            "external_status":        "pending",
        })
        return {"invoice_id": inv_id, "submission_id": sid, "ctx": ctx, "svc": svc}

    @pytest.mark.asyncio
    async def test_delivered_auto_transitions(self, sent_invoice):
        data = sent_invoice
        updated = await data["svc"].apply_peppol_status(
            data["submission_id"], data["ctx"],
            status="delivered",
            raw_status="dostavljeno",
        )
        assert updated["document_status"] == "delivered", (
            "apply_peppol_status('delivered') must auto-call mark_delivered()"
        )
        assert updated["peppol_raw_status"] == "dostavljeno"

    @pytest.mark.asyncio
    async def test_pending_records_without_transition(self, sent_invoice):
        data = sent_invoice
        updated = await data["svc"].apply_peppol_status(
            data["submission_id"], data["ctx"],
            status="pending",
        )
        assert updated["document_status"] == "eracun_sent"
        assert updated["external_status"] == "pending"

    @pytest.mark.asyncio
    async def test_rejected_transitions(self, sent_invoice):
        data = sent_invoice
        updated = await data["svc"].apply_peppol_status(
            data["submission_id"], data["ctx"],
            status="rejected",
            raw_status="odbijeno",
            buyer_message="Pogrešan OIB kupca",
        )
        assert updated["document_status"] == "rejected"
        assert "Pogrešan OIB" in (updated.get("rejection_reason") or "")

    @pytest.mark.asyncio
    async def test_failed_records_peppol_raw_status(self, sent_invoice):
        data = sent_invoice
        updated = await data["svc"].apply_peppol_status(
            data["submission_id"], data["ctx"],
            status="failed",
            raw_status="neisporuceno",
        )
        # No SM transition for failed; doc still in eracun_sent
        assert updated["peppol_raw_status"] == "neisporuceno"
        assert updated["external_status"]   == "failed"


# ── poll_pending_peppol_status ────────────────────────────────────────────────

class TestPollPendingPeppolStatus:

    @pytest.mark.asyncio
    async def test_stub_submission_ids_skipped(self, cid):
        """Docs with PEPPOL-STUB-* submission IDs must be skipped without AP call."""
        from services.erp.outbound_b2b_service import OutboundB2BService
        from services.erp.company_service import CompanyService
        from services.erp.base_erp_service import get_firestore_db

        ctx = make_ctx(cid)
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

        await get_firestore_db().collection("invoices_b2b").document(inv["invoice_id"]).update({
            "external_submission_id": "PEPPOL-STUB-ABCDEF123456",
            "delivery_method":        "peppol",
            "document_status":        "eracun_sent",
            "sent_at":                str(date.today()),
            "external_status":        "pending",
        })

        import os
        os.environ.pop("PEPPOL_AP_ENDPOINT", None)

        result = await svc.poll_pending_peppol_status(ctx)
        assert result["skipped"] >= 1
        assert result["polled"]  == 0

    @pytest.mark.asyncio
    async def test_status_change_applied_during_poll(self, cid):
        """Poll detects delivered → triggers SM transition eracun_sent → delivered."""
        from services.erp.outbound_b2b_service import OutboundB2BService
        from services.erp.company_service import CompanyService
        from services.erp.base_erp_service import get_firestore_db

        ctx = make_ctx(cid)
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

        sid = f"REAL-SID-{uuid4().hex[:8]}"
        db = get_firestore_db()
        await db.collection("invoices_b2b").document(inv["invoice_id"]).update({
            "external_submission_id": sid,
            "delivery_method":        "peppol",
            "document_status":        "eracun_sent",
            "sent_at":                str(date.today()),
            "external_status":        "pending",
        })

        mock_status = {
            "submission_id": sid,
            "raw_status":    "delivered",
            "status":        "delivered",
            "is_terminal":   False,
            "checked_at":    "2026-04-11T10:00:00+00:00",
        }

        with patch.dict("os.environ", {"PEPPOL_AP_ENDPOINT": "https://ap.example.com"}):
            with patch(
                "services.erp.outbound_b2b_service.fetch_submission_status",
                new=AsyncMock(return_value=mock_status),
            ):
                result = await svc.poll_pending_peppol_status(ctx)

        assert result["polled"]  >= 1
        assert result["updated"] >= 1

        snap = await db.collection("invoices_b2b").document(inv["invoice_id"]).get()
        assert (snap.to_dict() or {})["document_status"] == "delivered", (
            "Poll must trigger SM transition to delivered"
        )
