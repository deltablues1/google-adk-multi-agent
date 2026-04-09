"""
Outbound B2B Archive Tests (Faza 2C)
======================================
Tests for:
  - _build_meta_json schema                              [unit]
  - New archive tracking fields on created docs          [integration]
  - POST /outbound-b2b/{id}/archive                     [API]
  - GET  /outbound-b2b/pending-archive                  [API]
  - POST /outbound-b2b/retry-archive                    [API]

Drive API calls are fully mocked — no real Drive connection required.
Firestore uses real async client (same pattern as other ERP tests).
"""

import asyncio
import json
import pytest
from contextlib import contextmanager
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
            user_id="test-user-archive",
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
    return f"test_archive_{uuid4().hex}"


@pytest.fixture(scope="module")
def app(company_id):
    return build_test_app(company_id)


# ── Helpers ──────────────────────────────────────────────────────────────────

_SAMPLE_ITEMS = [
    {
        "description": "Konzultantske usluge",
        "name": "Konzultantske usluge",
        "quantity": 5,
        "unit": "sat",
        "unit_price": 200.00,
        "vat_rate": 25,
    }
]


def _b2b_payload(**overrides) -> dict:
    base = {
        "customer_name":  "Kupac d.o.o.",
        "customer_oib":   "12345678901",
        "seller_name":    "Prodavač d.o.o.",
        "seller_oib":     "98765432100",
        "seller_iban":    "HR1210010051863000160",
        "issue_date":     str(date(2026, 4, 1)),
        "due_date":       str(date(2026, 5, 1)),
        "items":          _SAMPLE_ITEMS,
    }
    base.update(overrides)
    return base


async def _create_invoice(client) -> dict:
    r = await client.post("/api/erp/outbound-b2b", json=_b2b_payload())
    assert r.status_code == 200, r.text
    return r.json()


async def _create_and_issue(client) -> dict:
    """Create → approve → issue.  Returns issued doc."""
    doc = await _create_invoice(client)
    inv_id = doc["invoice_id"]
    await client.post(f"/api/erp/outbound-b2b/{inv_id}/approve")
    r = await client.post(f"/api/erp/outbound-b2b/{inv_id}/issue")
    assert r.status_code == 200
    return r.json()


@contextmanager
def _archive_patches(pdf_fails: bool = False):
    """
    Context manager that mocks all Drive + PDF calls needed for archive tests.

    Args:
        pdf_fails: If True, the PDF renderer raises an exception (tests graceful fallback).
    """
    mock_nav = MagicMock()
    mock_nav.get_folder_id = MagicMock(return_value="archive-out-b2b-root-id")

    pdf_patch = (
        patch(
            "services.erp.outbound_pdf_renderer.render_invoice_pdf",
            side_effect=RuntimeError("PDF render failed"),
        )
        if pdf_fails
        else patch(
            "services.erp.outbound_pdf_renderer.render_invoice_pdf",
            return_value=b"%PDF-test",
        )
    )

    with (
        patch("tools.drive_navigator.get_drive_navigator",
              new=AsyncMock(return_value=mock_nav)),
        patch("services.erp.outbound_archive_service._get_or_create_folder",
              new=AsyncMock(return_value="month-folder-id")),
        patch("services.erp.outbound_archive_service._upload_bytes_to_drive",
              new=AsyncMock(return_value={"id": "fake-drive-file-id", "name": "test.xml"})),
        patch("tools.google_api_client.create_api_client_auto",
              return_value=MagicMock(credentials=MagicMock())),
        pdf_patch,
    ):
        yield


# ── Unit tests: meta JSON schema ─────────────────────────────────────────────

@pytest.mark.unit
class TestMetaJsonSchema:
    """Sync unit tests — no asyncio marker needed."""

    def test_meta_json_has_required_fields(self):
        from services.erp.outbound_archive_service import _build_meta_json
        doc = {
            "invoice_id":    "inv-123",
            "display_id":    "B2B-2026-0001",
            "document_status": "accepted",
            "delivery_method": "peppol",
            "delivery_target": "HR:OIB:12345678901",
            "external_submission_id": "PEPPOL-STUB-abc",
            "external_status": "accepted",
            "sent_at":       "2026-04-04T10:00:00+00:00",
            "delivered_at":  "2026-04-05T10:00:00+00:00",
            "accepted_at":   "2026-04-06T10:00:00+00:00",
            "rejected_at":   None,
            "send_attempts": 1,
        }
        archived_at = "2026-04-06T12:00:00+00:00"
        raw = _build_meta_json(doc, archived_at=archived_at)
        meta = json.loads(raw)

        assert meta["schema_version"] == 2
        assert meta["invoice_id"] == "inv-123"
        assert meta["display_id"] == "B2B-2026-0001"
        assert meta["document_status"] == "accepted"
        assert meta["delivery_method"] == "peppol"
        assert meta["external_submission_id"] == "PEPPOL-STUB-abc"
        assert meta["archived_at"] == archived_at
        assert meta["rejected_at"] is None
        assert meta["send_attempts"] == 1
        assert "archive_pdf_file_id" in meta

    def test_meta_json_is_valid_utf8_bytes(self):
        from services.erp.outbound_archive_service import _build_meta_json
        doc = {"display_id": "B2B-2026-0001", "document_status": "issued"}
        raw = _build_meta_json(doc, archived_at="2026-04-01T00:00:00+00:00")
        assert isinstance(raw, bytes)
        decoded = raw.decode("utf-8")
        assert json.loads(decoded)["schema_version"] == 2

    def test_meta_json_missing_optional_fields_default_to_none(self):
        from services.erp.outbound_archive_service import _build_meta_json
        doc = {}   # empty doc — all fields optional
        raw = _build_meta_json(doc, archived_at="2026-04-01T00:00:00+00:00")
        meta = json.loads(raw)
        assert meta["invoice_id"] is None
        assert meta["send_attempts"] == 0


# ── Archive tracking fields on created doc ───────────────────────────────────

@_async_mark
class TestArchiveFieldsOnCreate:

    async def test_new_doc_has_all_archive_tracking_fields(self, app):
        """Created doc must carry all 9 archive tracking fields."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_invoice(client)

        assert doc["archive_status"]          == "not_archived"
        assert doc["archive_attempts"]        == 0
        assert doc["last_archive_attempt_at"] is None
        assert doc["archived_at"]             is None
        assert doc["archive_error"]           is None
        assert doc["archive_folder_id"]       is None
        assert doc["archive_drive_file_id"]   is None
        assert doc["archive_ubl_file_id"]     is None
        assert doc["archive_meta_file_id"]    is None
        assert doc["archive_pdf_file_id"]     is None


# ── POST /outbound-b2b/{id}/archive ──────────────────────────────────────────

@_async_mark
class TestArchiveDocumentEndpoint:

    async def test_archive_issued_invoice_succeeds(self, app):
        """Archive an issued invoice → both file IDs set, status = archived."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_and_issue(client)
            with _archive_patches():
                r = await client.post(f"/api/erp/outbound-b2b/{doc['invoice_id']}/archive")

        assert r.status_code == 200
        result = r.json()
        assert result["archive_status"] == "archived"

    async def test_archive_sets_both_file_ids(self, app):
        """Both archive_ubl_file_id and archive_meta_file_id must be populated."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_and_issue(client)
            with _archive_patches():
                r = await client.post(f"/api/erp/outbound-b2b/{doc['invoice_id']}/archive")

        result = r.json()
        assert result.get("archive_ubl_file_id"),  "archive_ubl_file_id must be set"
        assert result.get("archive_meta_file_id"), "archive_meta_file_id must be set"

    async def test_archive_backward_compat_drive_file_id(self, app):
        """archive_drive_file_id must equal archive_ubl_file_id (backward-compat alias)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_and_issue(client)
            with _archive_patches():
                r = await client.post(f"/api/erp/outbound-b2b/{doc['invoice_id']}/archive")

        result = r.json()
        assert result["archive_drive_file_id"] == result["archive_ubl_file_id"]

    async def test_archive_sets_archived_at_and_folder_id(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_and_issue(client)
            with _archive_patches():
                r = await client.post(f"/api/erp/outbound-b2b/{doc['invoice_id']}/archive")

        result = r.json()
        assert result.get("archived_at")       is not None
        assert result.get("archive_folder_id") is not None

    async def test_archive_increments_attempt_count(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_and_issue(client)
            with _archive_patches():
                r = await client.post(f"/api/erp/outbound-b2b/{doc['invoice_id']}/archive")

        assert r.json()["archive_attempts"] == 1

    async def test_archive_idempotent_second_call(self, app):
        """Second archive call returns archived state without touching Drive."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_and_issue(client)
            inv_id = doc["invoice_id"]

            with _archive_patches():
                await client.post(f"/api/erp/outbound-b2b/{inv_id}/archive")
                # Second call — early return, no Drive calls needed
                r = await client.post(f"/api/erp/outbound-b2b/{inv_id}/archive")

        assert r.status_code == 200
        assert r.json()["archive_status"] == "archived"

    async def test_archive_draft_without_ubl_returns_422(self, app):
        """Draft invoice (no UBL) → 422 UBL_NOT_GENERATED."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_invoice(client)
            r = await client.post(f"/api/erp/outbound-b2b/{doc['invoice_id']}/archive")

        assert r.status_code == 422
        assert r.json()["code"] == "UBL_NOT_GENERATED"

    async def test_archive_sets_pdf_file_id(self, app):
        """archive_pdf_file_id must be populated when PDF render+upload succeeds."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_and_issue(client)
            with _archive_patches():
                r = await client.post(f"/api/erp/outbound-b2b/{doc['invoice_id']}/archive")

        result = r.json()
        assert result.get("archive_pdf_file_id"), "archive_pdf_file_id must be set on success"

    async def test_archive_succeeds_even_if_pdf_fails(self, app):
        """PDF render failure must NOT block archive — UBL+meta still archived, pdf_file_id=None."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_and_issue(client)
            with _archive_patches(pdf_fails=True):
                r = await client.post(f"/api/erp/outbound-b2b/{doc['invoice_id']}/archive")

        assert r.status_code == 200
        result = r.json()
        assert result["archive_status"] == "archived",  "archive_status must be 'archived' even when PDF fails"
        assert result.get("archive_ubl_file_id"),        "UBL must still be uploaded"
        assert result.get("archive_meta_file_id"),       "meta must still be uploaded"
        assert result.get("archive_pdf_file_id") is None, "archive_pdf_file_id must be None on PDF failure"

    async def test_archive_drive_failure_sets_failed_status(self, app):
        """When Drive upload fails, doc gets archive_status=failed and 422 is returned."""
        mock_nav = MagicMock()
        mock_nav.get_folder_id = MagicMock(return_value="some-root-id")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_and_issue(client)
            inv_id = doc["invoice_id"]

            with (
                patch("tools.drive_navigator.get_drive_navigator",
                      new=AsyncMock(return_value=mock_nav)),
                patch("services.erp.outbound_archive_service._get_or_create_folder",
                      new=AsyncMock(return_value="folder-id")),
                patch("services.erp.outbound_archive_service._upload_bytes_to_drive",
                      new=AsyncMock(side_effect=Exception("Drive quota exceeded"))),
                patch("tools.google_api_client.create_api_client_auto",
                      return_value=MagicMock(credentials=MagicMock())),
            ):
                r = await client.post(f"/api/erp/outbound-b2b/{inv_id}/archive")

        assert r.status_code == 422
        assert r.json()["code"] == "ARCHIVE_FAILED"

        # Verify failed state was persisted
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            state = await client.get(f"/api/erp/outbound-b2b/{inv_id}")
        doc_state = state.json()
        assert doc_state["archive_status"] == "failed"
        assert doc_state.get("archive_error")
        assert doc_state["archive_attempts"] == 1


# ── GET /outbound-b2b/pending-archive ────────────────────────────────────────

@_async_mark
class TestPendingArchiveEndpoint:

    async def test_pending_archive_lists_issued_docs(self, app):
        """Issued invoice with UBL must appear in pending-archive."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_and_issue(client)
            inv_id = doc["invoice_id"]
            r = await client.get("/api/erp/outbound-b2b/pending-archive")

        assert r.status_code == 200
        items = r.json()
        assert any(d["invoice_id"] == inv_id for d in items), (
            "Issued invoice with UBL should appear in pending-archive"
        )

    async def test_pending_archive_excludes_archived_docs(self, app):
        """Successfully archived invoice must NOT appear in pending-archive."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_and_issue(client)
            inv_id = doc["invoice_id"]

            with _archive_patches():
                await client.post(f"/api/erp/outbound-b2b/{inv_id}/archive")

            r = await client.get("/api/erp/outbound-b2b/pending-archive")

        assert r.status_code == 200
        assert not any(d["invoice_id"] == inv_id for d in r.json()), (
            "Archived invoice must not appear in pending-archive"
        )

    async def test_pending_archive_excludes_draft_docs(self, app):
        """Draft invoice (no UBL) must NOT appear in pending-archive."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_invoice(client)
            inv_id = doc["invoice_id"]
            r = await client.get("/api/erp/outbound-b2b/pending-archive")

        assert r.status_code == 200
        assert not any(d["invoice_id"] == inv_id for d in r.json())

    async def test_pending_archive_strips_ubl_xml(self, app):
        """ubl_xml must NOT be returned in pending-archive list response."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await _create_and_issue(client)
            r = await client.get("/api/erp/outbound-b2b/pending-archive")

        assert r.status_code == 200
        for item in r.json():
            assert "ubl_xml" not in item, "ubl_xml must be stripped from pending-archive response"


# ── POST /outbound-b2b/retry-archive ────────────────────────────────────────

@_async_mark
class TestRetryArchiveEndpoint:

    async def test_retry_archive_returns_summary_keys(self, app):
        """retry-archive must return {attempted, succeeded, failed, skipped}."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with _archive_patches():
                r = await client.post("/api/erp/outbound-b2b/retry-archive")

        assert r.status_code == 200
        summary = r.json()
        assert "attempted" in summary
        assert "succeeded" in summary
        assert "failed"    in summary
        assert "skipped"   in summary

    async def test_retry_archive_skips_max_attempts_exceeded(self, app):
        """Invoice with archive_attempts >= max_attempts must be skipped, not attempted."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Create invoice that has already hit max attempts — simulate by
            # failing archive twice with max_attempts=1
            doc = await _create_and_issue(client)
            inv_id = doc["invoice_id"]
            mock_nav = MagicMock()
            mock_nav.get_folder_id = MagicMock(return_value="root-id")

            # First failed attempt
            with (
                patch("tools.drive_navigator.get_drive_navigator",
                      new=AsyncMock(return_value=mock_nav)),
                patch("services.erp.outbound_archive_service._get_or_create_folder",
                      new=AsyncMock(return_value="folder-id")),
                patch("services.erp.outbound_archive_service._upload_bytes_to_drive",
                      new=AsyncMock(side_effect=Exception("Drive error"))),
                patch("tools.google_api_client.create_api_client_auto",
                      return_value=MagicMock(credentials=MagicMock())),
            ):
                await client.post(f"/api/erp/outbound-b2b/{inv_id}/archive")

            # Retry with max_attempts=1 — invoice already has archive_attempts=1 → skipped
            with _archive_patches():
                r = await client.post("/api/erp/outbound-b2b/retry-archive?max_attempts=1")

        assert r.status_code == 200
        summary = r.json()
        # The invoice we just failed must have been skipped
        assert summary["skipped"] >= 1

    async def test_retry_archive_succeeds_on_retry_after_failure(self, app):
        """After a failed archive attempt, retry-archive should succeed (attempts < max)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_and_issue(client)
            inv_id = doc["invoice_id"]
            mock_nav = MagicMock()
            mock_nav.get_folder_id = MagicMock(return_value="root-id")

            # First attempt fails
            with (
                patch("tools.drive_navigator.get_drive_navigator",
                      new=AsyncMock(return_value=mock_nav)),
                patch("services.erp.outbound_archive_service._get_or_create_folder",
                      new=AsyncMock(return_value="folder-id")),
                patch("services.erp.outbound_archive_service._upload_bytes_to_drive",
                      new=AsyncMock(side_effect=Exception("transient error"))),
                patch("tools.google_api_client.create_api_client_auto",
                      return_value=MagicMock(credentials=MagicMock())),
            ):
                await client.post(f"/api/erp/outbound-b2b/{inv_id}/archive")

            # Retry with max_attempts=3 — attempt 1 < 3 → should retry and succeed
            with _archive_patches():
                r = await client.post("/api/erp/outbound-b2b/retry-archive?max_attempts=3")

        assert r.status_code == 200
        summary = r.json()
        assert summary["succeeded"] >= 1

        # Verify the invoice is now archived
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            state = await client.get(f"/api/erp/outbound-b2b/{inv_id}")
        assert state.json()["archive_status"] == "archived"
