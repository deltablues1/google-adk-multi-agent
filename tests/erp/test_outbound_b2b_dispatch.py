"""
Outbound B2B Dispatch Tests (Faza 2B)
=======================================
Tests for:
  - outbound_dispatch_service adapters (manual, email, peppol) [unit]
  - OutboundB2BService.send() real dispatch integration         [integration]
  - OutboundB2BService.resend() retry logic                    [integration]
  - OutboundB2BService.sync_external_status() auto-transitions [integration]
  - POST /outbound-b2b/{id}/resend                             [API]
  - POST /outbound-b2b/{id}/sync-status                        [API]
  - GET  /outbound-b2b/pending-ack                             [API]
  - GET  /outbound-b2b/send-failures                           [API]
  - POST /outbound-b2b/retry-send-failures                     [API]
  - New dispatch fields present on created docs                [API]

Gmail and Peppol calls are fully mocked — no real transport.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import date

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

_ITEMS = [
    {"description": "Usluga X", "quantity": 2, "unit_price": 200.0, "vat_rate": 25},
]


def _b2b_payload(**overrides) -> dict:
    base = {
        "customer_name": "Kupac d.o.o.",
        "customer_oib": "12345678901",
        "seller_name": "Prodavatelj d.o.o.",
        "seller_oib": "98765432100",
        "seller_iban": "HR1210010051863000160",
        "issue_date": str(date(2026, 4, 1)),
        "due_date": str(date(2026, 5, 1)),
        "items": _ITEMS,
    }
    base.update(overrides)
    return base


async def _create_and_issue(client) -> dict:
    """Create → approve → issue. Returns issued doc."""
    r = await client.post("/api/erp/outbound-b2b", json=_b2b_payload())
    assert r.status_code == 200, r.text
    inv_id = r.json()["invoice_id"]
    await client.post(f"/api/erp/outbound-b2b/{inv_id}/approve")
    r = await client.post(f"/api/erp/outbound-b2b/{inv_id}/issue")
    assert r.json()["document_status"] == "issued"
    return r.json()


# ── Unit tests: dispatch adapters ───────────────────────────────────────────

@pytest.mark.unit
class TestDispatchAdapters:

    def _make_doc(self, **overrides):
        base = {
            "invoice_id":   str(uuid4()),
            "display_id":   "B2B-2026-000001",
            "seller_name":  "Prodavatelj d.o.o.",
            "customer_name": "Kupac d.o.o.",
            "issue_date":   "2026-04-01",
            "total_gross":  500.0,
            "currency":     "EUR",
            "ubl_xml":      "<?xml version='1.0'?><Invoice/>",
        }
        base.update(overrides)
        return base

    def test_manual_returns_ok(self):
        import asyncio
        from services.erp.outbound_dispatch_service import dispatch_invoice
        doc = self._make_doc()
        result = asyncio.run(
            dispatch_invoice(doc, "manual", "", "")
        )
        assert result["ok"] is True
        assert result["method"] == "manual"
        assert result["sent_at"] is not None

    def test_manual_with_ref_stores_submission_id(self):
        import asyncio
        from services.erp.outbound_dispatch_service import dispatch_invoice
        doc = self._make_doc()
        result = asyncio.run(
            dispatch_invoice(doc, "manual", "", "MANUAL-REF-001")
        )
        assert result["ok"] is True
        assert result["external_submission_id"] == "MANUAL-REF-001"

    def test_email_requires_valid_address(self):
        import asyncio
        from services.erp.outbound_dispatch_service import dispatch_invoice
        doc = self._make_doc()
        result = asyncio.run(
            dispatch_invoice(doc, "email", "not-an-email", "")
        )
        assert result["ok"] is False
        assert "email" in result["error"].lower()

    def test_email_requires_ubl_xml(self):
        import asyncio
        from services.erp.outbound_dispatch_service import dispatch_invoice
        doc = self._make_doc(ubl_xml=None)
        result = asyncio.run(
            dispatch_invoice(doc, "email", "buyer@test.hr", "")
        )
        assert result["ok"] is False

    def test_peppol_requires_participant_id(self):
        import asyncio
        from services.erp.outbound_dispatch_service import dispatch_invoice
        doc = self._make_doc()
        result = asyncio.run(
            dispatch_invoice(doc, "peppol", "", "")
        )
        assert result["ok"] is False
        assert "participant" in result["error"].lower()

    def test_peppol_stub_returns_synthetic_submission_id(self):
        import asyncio
        from services.erp.outbound_dispatch_service import dispatch_invoice
        doc = self._make_doc()
        result = asyncio.run(
            dispatch_invoice(doc, "peppol", "0007:HR98765432100", "")
        )
        assert result["ok"] is True
        assert result["_stub"] is True
        assert result["external_submission_id"].startswith("PEPPOL-STUB-")

    def test_unknown_method_returns_error(self):
        import asyncio
        from services.erp.outbound_dispatch_service import dispatch_invoice
        doc = self._make_doc()
        result = asyncio.run(
            dispatch_invoice(doc, "fax", "", "")
        )
        assert result["ok"] is False


# ── Dispatch fields present on created docs ──────────────────────────────────

@_async_mark
class TestDispatchFieldsOnCreate:

    async def test_new_doc_has_dispatch_fields(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/api/erp/outbound-b2b", json=_b2b_payload())
        doc = r.json()
        assert doc["send_attempts"] == 0
        assert doc["last_send_attempt_at"] is None
        assert doc["last_send_error"] is None
        assert doc["external_submission_id"] is None
        assert doc["external_status"] is None
        assert doc["next_retry_at"] is None


# ── send() with real dispatch (mocked transport) ─────────────────────────────

@_async_mark
class TestSendRealDispatch:

    async def test_send_manual_succeeds(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_and_issue(client)
            r = await client.post(
                f"/api/erp/outbound-b2b/{doc['invoice_id']}/send",
                json={"delivery_method": "manual", "delivery_target": ""},
            )
        assert r.status_code == 200
        result = r.json()
        assert result["document_status"] == "eracun_sent"
        assert result["send_attempts"] == 1
        assert result["last_send_error"] is None
        assert result["next_retry_at"] is None

    async def test_send_manual_stores_ref_as_submission_id(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_and_issue(client)
            r = await client.post(
                f"/api/erp/outbound-b2b/{doc['invoice_id']}/send",
                json={"delivery_method": "manual", "delivery_target": "", "delivery_ref": "MANUAL-PICKUP-001"},
            )
        assert r.status_code == 200
        assert r.json()["external_submission_id"] == "MANUAL-PICKUP-001"

    async def test_send_email_success_mocked(self, app):
        """Email send via Gmail API — mock the transport."""
        mock_gmail_result = {"id": "gmail-msg-abc123", "thread_id": "t1", "status": "sent"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_and_issue(client)

            with (
                patch("tools.google_api_client.create_api_client_auto",
                      return_value=MagicMock(credentials=MagicMock())),
                patch("tools.api_implementations.gmail_api.gmail_send_message",
                      new=AsyncMock(return_value=mock_gmail_result)),
            ):
                r = await client.post(
                    f"/api/erp/outbound-b2b/{doc['invoice_id']}/send",
                    json={"delivery_method": "email", "delivery_target": "buyer@firma.hr"},
                )

        assert r.status_code == 200
        result = r.json()
        assert result["document_status"] == "eracun_sent"
        assert result["external_submission_id"] == "gmail-msg-abc123"
        assert result["send_attempts"] == 1

    async def test_send_email_failure_records_error(self, app):
        """When Gmail raises, send() stores last_send_error and does NOT transition status."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_and_issue(client)

            with (
                patch("tools.google_api_client.create_api_client_auto",
                      return_value=MagicMock(credentials=MagicMock())),
                patch("tools.api_implementations.gmail_api.gmail_send_message",
                      new=AsyncMock(side_effect=Exception("SMTP connection refused"))),
            ):
                r = await client.post(
                    f"/api/erp/outbound-b2b/{doc['invoice_id']}/send",
                    json={"delivery_method": "email", "delivery_target": "buyer@firma.hr"},
                )

        assert r.status_code == 422
        assert r.json()["code"] == "SEND_FAILED"

        # Verify doc is still 'issued' with error recorded
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            get_r = await client.get(f"/api/erp/outbound-b2b/{doc['invoice_id']}")
        state = get_r.json()
        assert state["document_status"] == "issued"
        assert state["last_send_error"] is not None
        assert state["send_attempts"] == 1
        assert state["next_retry_at"] is not None

    async def test_send_peppol_stub(self, app):
        """Peppol stub dispatch succeeds with synthetic submission ID."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_and_issue(client)
            r = await client.post(
                f"/api/erp/outbound-b2b/{doc['invoice_id']}/send",
                json={"delivery_method": "peppol", "delivery_target": "0007:HR98765432100"},
            )
        assert r.status_code == 200
        result = r.json()
        assert result["document_status"] == "eracun_sent"
        assert result["external_submission_id"].startswith("PEPPOL-STUB-")


# ── resend() ────────────────────────────────────────────────────────────────

@_async_mark
class TestResend:

    async def _create_issued_with_failed_send(self, client) -> str:
        """Create + issue + trigger send failure. Returns invoice_id."""
        doc = await _create_and_issue(client)
        inv_id = doc["invoice_id"]
        with (
            patch("tools.google_api_client.create_api_client_auto",
                  return_value=MagicMock(credentials=MagicMock())),
            patch("tools.api_implementations.gmail_api.gmail_send_message",
                  new=AsyncMock(side_effect=Exception("timeout"))),
        ):
            await client.post(
                f"/api/erp/outbound-b2b/{inv_id}/send",
                json={"delivery_method": "email", "delivery_target": "b@b.hr"},
            )
        return inv_id

    async def test_resend_after_failure_succeeds(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            inv_id = await self._create_issued_with_failed_send(client)

            with (
                patch("tools.google_api_client.create_api_client_auto",
                      return_value=MagicMock(credentials=MagicMock())),
                patch("tools.api_implementations.gmail_api.gmail_send_message",
                      new=AsyncMock(return_value={"id": "gmail-retry-123", "status": "sent"})),
            ):
                r = await client.post(
                    f"/api/erp/outbound-b2b/{inv_id}/resend",
                    json={"delivery_method": "email", "delivery_target": "b@b.hr"},
                )

        assert r.status_code == 200
        result = r.json()
        assert result["document_status"] == "eracun_sent"
        assert result["last_send_error"] is None
        assert result["send_attempts"] == 2   # original attempt + retry

    async def test_resend_with_manual_uses_existing_metadata(self, app):
        """Resend with no body uses doc's stored delivery_method/target."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            inv_id = await self._create_issued_with_failed_send(client)
            # Re-send using manual (no body needed)
            r = await client.post(
                f"/api/erp/outbound-b2b/{inv_id}/resend",
                json={"delivery_method": "manual", "delivery_target": ""},
            )
        assert r.status_code == 200
        assert r.json()["document_status"] == "eracun_sent"

    async def test_resend_from_draft_returns_422(self, app):
        """Cannot resend a draft (no UBL, wrong status)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/api/erp/outbound-b2b", json=_b2b_payload())
            inv_id = r.json()["invoice_id"]
            r = await client.post(
                f"/api/erp/outbound-b2b/{inv_id}/resend",
                json={"delivery_method": "manual", "delivery_target": ""},
            )
        assert r.status_code == 422


# ── sync_external_status() ──────────────────────────────────────────────────

@_async_mark
class TestSyncExternalStatus:

    async def _create_sent(self, client) -> str:
        """Create + issue + send (manual), return invoice_id."""
        doc = await _create_and_issue(client)
        inv_id = doc["invoice_id"]
        await client.post(
            f"/api/erp/outbound-b2b/{inv_id}/send",
            json={"delivery_method": "manual", "delivery_target": ""},
        )
        return inv_id

    async def test_sync_delivered_auto_transitions(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            inv_id = await self._create_sent(client)
            r = await client.post(
                f"/api/erp/outbound-b2b/{inv_id}/sync-status",
                json={"external_status": "delivered", "external_ref": "AP-CONFIRM-001"},
            )
        assert r.status_code == 200
        result = r.json()
        assert result["document_status"] == "delivered"
        assert result["external_status"] == "delivered"

    async def test_sync_accepted_from_delivered_auto_transitions(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            inv_id = await self._create_sent(client)
            await client.post(f"/api/erp/outbound-b2b/{inv_id}/delivered")
            r = await client.post(
                f"/api/erp/outbound-b2b/{inv_id}/sync-status",
                json={"external_status": "accepted"},
            )
        assert r.status_code == 200
        assert r.json()["document_status"] == "accepted"

    async def test_sync_pending_only_records_external_status(self, app):
        """'pending' status is informational — no SM transition."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            inv_id = await self._create_sent(client)
            r = await client.post(
                f"/api/erp/outbound-b2b/{inv_id}/sync-status",
                json={"external_status": "pending"},
            )
        assert r.status_code == 200
        result = r.json()
        assert result["document_status"] == "eracun_sent"   # unchanged
        assert result["external_status"] == "pending"

    async def test_sync_failed_populates_failure_tracking_fields(self, app):
        """
        'failed' external status must populate last_send_error, next_retry_at,
        and increment send_attempts.

        Two sub-scenarios:
        A) doc in eracun_sent — failure fields recorded, document_status unchanged.
           resend() works from eracun_sent so operator can retry manually.
        B) doc in issued (AP rejected before send completed) — failure fields recorded
           AND doc appears in list_send_failures() / retry_send_failures() flow.
        """
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # --- Scenario A: eracun_sent doc ---
            inv_id_sent = await self._create_sent(client)
            r = await client.post(
                f"/api/erp/outbound-b2b/{inv_id_sent}/sync-status",
                json={"external_status": "failed", "external_ref": "AP-ERR-999"},
            )
            assert r.status_code == 200
            result = r.json()
            assert result["document_status"] == "eracun_sent"   # SM unchanged
            assert result["external_status"] == "failed"
            assert result.get("last_send_error"), "last_send_error should be set"
            assert "AP-ERR-999" in result["last_send_error"]
            assert result.get("next_retry_at") is not None
            assert isinstance(result.get("send_attempts"), int) and result["send_attempts"] >= 1

            # --- Scenario B: issued doc (AP rejection before successful send) ---
            inv_issued = await _create_and_issue(client)
            inv_id_issued = inv_issued["invoice_id"]
            r2 = await client.post(
                f"/api/erp/outbound-b2b/{inv_id_issued}/sync-status",
                json={"external_status": "failed", "external_ref": "AP-PRE-SEND-FAIL"},
            )
            assert r2.status_code == 200
            result2 = r2.json()
            assert result2["document_status"] == "issued"        # SM unchanged
            assert result2.get("last_send_error")
            assert "AP-PRE-SEND-FAIL" in result2["last_send_error"]
            assert result2.get("next_retry_at") is not None
            assert result2.get("send_attempts", 0) >= 1

            # Scenario B doc (issued + last_send_error) must appear in send-failures
            sf = await client.get("/api/erp/outbound-b2b/send-failures")
        assert sf.status_code == 200
        assert any(d["invoice_id"] == inv_id_issued for d in sf.json())


# ── Collection-level dispatch endpoints ─────────────────────────────────────

@_async_mark
class TestDispatchCollectionEndpoints:

    async def test_pending_ack_returns_sent_and_delivered(self, app):
        """pending-ack lists eracun_sent and delivered invoices (email adapter, ack_expected=True)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Create + send one invoice via email (ack_expected=True)
            doc = await _create_and_issue(client)
            inv_id = doc["invoice_id"]
            with (
                patch("tools.google_api_client.create_api_client_auto",
                      return_value=MagicMock(credentials=MagicMock())),
                patch("tools.api_implementations.gmail_api.gmail_send_message",
                      new=AsyncMock(return_value={"id": "pending-ack-test"})),
            ):
                await client.post(
                    f"/api/erp/outbound-b2b/{inv_id}/send",
                    json={"delivery_method": "email", "delivery_target": "buyer@test.hr"},
                )
            r = await client.get("/api/erp/outbound-b2b/pending-ack")
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        assert any(d["invoice_id"] == inv_id for d in items)
        # UBL XML must not be in list responses
        for item in items:
            assert "ubl_xml" not in item

    async def test_pending_ack_includes_overdue_fields(self, app):
        """pending-ack response items carry days_waiting, ack_deadline, is_ack_overdue."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_and_issue(client)
            inv_id = doc["invoice_id"]
            with (
                patch("tools.google_api_client.create_api_client_auto",
                      return_value=MagicMock(credentials=MagicMock())),
                patch("tools.api_implementations.gmail_api.gmail_send_message",
                      new=AsyncMock(return_value={"id": "overdue-fields-test"})),
            ):
                await client.post(
                    f"/api/erp/outbound-b2b/{inv_id}/send",
                    json={"delivery_method": "email", "delivery_target": "buyer@test.hr"},
                )
            r = await client.get("/api/erp/outbound-b2b/pending-ack")
        assert r.status_code == 200
        items = r.json()
        target = next((d for d in items if d["invoice_id"] == inv_id), None)
        assert target is not None, "Just-sent invoice should appear in pending-ack"
        # Overdue fields must be present
        assert "days_waiting" in target, "days_waiting missing from pending-ack item"
        assert "ack_deadline" in target, "ack_deadline missing from pending-ack item"
        assert "is_ack_overdue" in target, "is_ack_overdue missing from pending-ack item"
        # A just-sent invoice cannot be overdue
        assert target["is_ack_overdue"] is False
        # days_waiting is non-negative
        assert target["days_waiting"] is not None
        assert target["days_waiting"] >= 0

    async def test_send_failures_returns_issued_with_errors(self, app):
        """send-failures lists issued invoices with last_send_error set."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_and_issue(client)
            inv_id = doc["invoice_id"]
            # Trigger a failed send
            with (
                patch("tools.google_api_client.create_api_client_auto",
                      return_value=MagicMock(credentials=MagicMock())),
                patch("tools.api_implementations.gmail_api.gmail_send_message",
                      new=AsyncMock(side_effect=Exception("network error"))),
            ):
                await client.post(
                    f"/api/erp/outbound-b2b/{inv_id}/send",
                    json={"delivery_method": "email", "delivery_target": "x@x.hr"},
                )
            r = await client.get("/api/erp/outbound-b2b/send-failures")
        assert r.status_code == 200
        items = r.json()
        assert any(d["invoice_id"] == inv_id for d in items)

    async def test_retry_send_failures_returns_summary(self, app):
        """retry-send-failures returns {attempted, succeeded, failed, skipped}."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # All retry candidates in this test used email delivery_method.
            # Patch Gmail to succeed so the retry works.
            with (
                patch("tools.google_api_client.create_api_client_auto",
                      return_value=MagicMock(credentials=MagicMock())),
                patch("tools.api_implementations.gmail_api.gmail_send_message",
                      new=AsyncMock(return_value={"id": "retry-gmail-ok", "status": "sent"})),
            ):
                r = await client.post("/api/erp/outbound-b2b/retry-send-failures")
        assert r.status_code == 200
        summary = r.json()
        assert "attempted" in summary
        assert "succeeded" in summary
        assert "failed" in summary
        assert "skipped" in summary
