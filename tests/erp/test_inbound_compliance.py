"""
Inbound Compliance Tests (Faza 1D + 1F)
=========================================
Tests for:
  - drive_archive_service.archive_inbound_document()  [1D]
  - VendorInvoiceService.archive_original_document()  [1D]
  - POST /vendor-invoices/{id}/archive-original       [1D]
  - GET  /vendor-invoices/inbound-compliance-report   [1F]
  - GET  /vendor-invoices/overdue-fiscalizations      [1F]
  - auto-archive branch in monitor_drive_invoices     [1D]

Drive API calls are mocked — no real Drive connection required.
Firestore uses the same real-but-isolated pattern as test_erp_api.py.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import date, timedelta

import httpx
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from services.erp.errors import BusinessError
from services.erp.request_context import ERPRequestContext
from web.erp_routes import router as erp_router, get_erp_ctx

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


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

async def _create_vendor_invoice(client, *, vendor_invoice_no: str = None) -> dict:
    """Create a minimal vendor invoice and return the JSON doc."""
    payload = {
        "vendor_name": "HT Test d.d.",
        "vendor_oib": "81793146560",
        "vendor_invoice_no": vendor_invoice_no or f"INV-{uuid4().hex[:6]}",
        "issue_date": "2026-03-01",
        "due_date": "2026-04-01",
        "received_date": "2026-03-02",
        "total_gross": 224.97,
        "vat_amount": 44.99,
        "subtotal_net": 179.98,
        "category": "services",
        "from_ocr": True,
    }
    resp = await client.post("/api/erp/vendor-invoices", json=payload)
    assert resp.status_code == 200, f"create failed: {resp.text}"
    return resp.json()


# ── drive_archive_service unit tests (mocked Drive) ─────────────────────────

class TestDriveArchiveService:

    @pytest.mark.asyncio
    async def test_archive_success_returns_ok(self):
        """archive_inbound_document returns ok=True and drive_folder_id on success."""
        from services.erp.drive_archive_service import archive_inbound_document

        mock_nav = MagicMock()
        mock_nav.get_folder_id.return_value = "archive_in_folder_id"

        with patch("tools.drive_navigator.get_drive_navigator",
                   new=AsyncMock(return_value=mock_nav)), \
             patch("services.erp.drive_archive_service.create_api_client_auto") as mock_api, \
             patch("services.erp.drive_archive_service.drive_search_files",
                   new=AsyncMock(return_value={"files": []})), \
             patch("services.erp.drive_archive_service.drive_create_folder",
                   new=AsyncMock(return_value={"id": "month_folder_id"})), \
             patch("services.erp.drive_archive_service.drive_move_file",
                   new=AsyncMock(return_value={"status": "moved"})):

            mock_api.return_value.credentials = MagicMock()
            result = await archive_inbound_document("file-123", issue_date="2026-03-28")

        assert result["ok"] is True
        assert result["drive_folder_id"] == "month_folder_id"
        assert "archived_at" in result

    @pytest.mark.asyncio
    async def test_archive_uses_existing_year_month_folders(self):
        """If YYYY/MM folders already exist, drive_search_files returns them (no create)."""
        from services.erp.drive_archive_service import archive_inbound_document

        mock_nav = MagicMock()
        mock_nav.get_folder_id.return_value = "archive_in_id"

        existing_year  = {"files": [{"id": "year_id"}]}
        existing_month = {"files": [{"id": "month_id"}]}
        search_side_effects = [existing_year, existing_month]

        create_folder_mock = AsyncMock()

        with patch("tools.drive_navigator.get_drive_navigator",
                   new=AsyncMock(return_value=mock_nav)), \
             patch("services.erp.drive_archive_service.create_api_client_auto") as mock_api, \
             patch("services.erp.drive_archive_service.drive_search_files",
                   new=AsyncMock(side_effect=search_side_effects)), \
             patch("services.erp.drive_archive_service.drive_create_folder",
                   new=create_folder_mock), \
             patch("services.erp.drive_archive_service.drive_move_file",
                   new=AsyncMock(return_value={"status": "moved"})):

            mock_api.return_value.credentials = MagicMock()
            result = await archive_inbound_document("file-123", issue_date="2026-03-28")

        assert result["ok"] is True
        assert result["drive_folder_id"] == "month_id"
        create_folder_mock.assert_not_called()  # No folders created — both existed

    @pytest.mark.asyncio
    async def test_archive_falls_back_to_today_if_no_issue_date(self):
        """If issue_date is None/empty, uses today's date for YYYY/MM."""
        from services.erp.drive_archive_service import archive_inbound_document

        mock_nav = MagicMock()
        mock_nav.get_folder_id.return_value = "archive_in_id"

        with patch("tools.drive_navigator.get_drive_navigator",
                   new=AsyncMock(return_value=mock_nav)), \
             patch("services.erp.drive_archive_service.create_api_client_auto") as mock_api, \
             patch("services.erp.drive_archive_service.drive_search_files",
                   new=AsyncMock(return_value={"files": []})), \
             patch("services.erp.drive_archive_service.drive_create_folder",
                   new=AsyncMock(return_value={"id": "folder_id"})), \
             patch("services.erp.drive_archive_service.drive_move_file",
                   new=AsyncMock(return_value={"status": "moved"})):

            mock_api.return_value.credentials = MagicMock()
            result = await archive_inbound_document("file-123", issue_date=None)

        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_archive_returns_error_if_navigator_not_ready(self):
        """If archive_in folder ID is not resolved, returns ok=False."""
        from services.erp.drive_archive_service import archive_inbound_document

        mock_nav = MagicMock()
        mock_nav.get_folder_id.return_value = None  # not resolved

        with patch("tools.drive_navigator.get_drive_navigator",
                   new=AsyncMock(return_value=mock_nav)):
            result = await archive_inbound_document("file-123")

        assert result["ok"] is False
        assert "archive_in" in result["error"]

    @pytest.mark.asyncio
    async def test_drive_move_failure_returns_ok_false(self):
        """If drive_move_file raises, returns ok=False without propagating."""
        from services.erp.drive_archive_service import archive_inbound_document

        mock_nav = MagicMock()
        mock_nav.get_folder_id.return_value = "archive_in_id"

        with patch("tools.drive_navigator.get_drive_navigator",
                   new=AsyncMock(return_value=mock_nav)), \
             patch("services.erp.drive_archive_service.create_api_client_auto") as mock_api, \
             patch("services.erp.drive_archive_service.drive_search_files",
                   new=AsyncMock(return_value={"files": []})), \
             patch("services.erp.drive_archive_service.drive_create_folder",
                   new=AsyncMock(return_value={"id": "folder_id"})), \
             patch("services.erp.drive_archive_service.drive_move_file",
                   new=AsyncMock(side_effect=Exception("Drive quota exceeded"))):

            mock_api.return_value.credentials = MagicMock()
            result = await archive_inbound_document("file-123", issue_date="2026-03-01")

        assert result["ok"] is False
        assert "quota" in result["error"].lower() or "Drive" in result["error"]


# ── archive_original_document service + API tests ────────────────────────────

class TestArchiveOriginalDocument:

    @pytest.mark.asyncio
    async def test_archive_original_no_drive_file_returns_422(self, app):
        """Invoice without drive_original_file_id returns validation error."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_vendor_invoice(client)
            vid = doc["vendor_invoice_id"]

            # No drive file → service raises ValidationError → 422
            resp = await client.post(f"/api/erp/vendor-invoices/{vid}/archive-original")
        assert resp.status_code == 422
        assert resp.json()["code"] == "NO_DRIVE_FILE"

    @pytest.mark.asyncio
    async def test_archive_unknown_invoice_returns_404(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/erp/vendor-invoices/nonexistent-id/archive-original")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_archive_idempotent_already_archived(self, app):
        """Calling archive on an already-archived invoice returns the current state, not an error."""
        from services.erp.vendor_invoice_service import get_vendor_invoice_service
        from services.erp.request_context import ERPRequestContext

        # Create and manually set archive_status=archived
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_vendor_invoice(client)
            vid = doc["vendor_invoice_id"]

        ctx = ERPRequestContext(
            user_id="test-user", company_id=app.dependency_overrides[get_erp_ctx]().company_id,
            role="owner", grants=["*"], denies=[], request_id="x"
        )
        svc = get_vendor_invoice_service()
        # Manually mark as archived
        await svc._get_repo().update(vid, ctx, {
            "archive_status": "archived",
            "archived_at": "2026-03-01T10:00:00+00:00",
            "drive_folder_id": "some-folder",
            "drive_original_file_id": "some-file",
        })

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/erp/vendor-invoices/{vid}/archive-original")

        assert resp.status_code == 200
        data = resp.json()
        assert data["archive_status"] == "archived"
        assert data.get("note") == "Already archived"


# ── inbound-compliance-report tests ─────────────────────────────────────────

class TestInboundComplianceReport:

    @pytest.mark.asyncio
    async def test_report_returns_200_with_correct_shape(self, app):
        """Compliance report endpoint returns expected structure."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/erp/vendor-invoices/inbound-compliance-report",
                                    params={"year": 2026, "month": 3})
        assert resp.status_code == 200
        data = resp.json()
        assert data["period"] == "2026-03"
        assert data["period_basis"] == "received_date"
        assert "total_invoices_received" in data
        assert "by_status" in data
        assert "sla_compliant" in data
        assert "overdue_fiscalization_count" in data
        assert "fisc_reported_this_period" in data
        assert "accepted_count" in data
        assert "rejected_count" in data
        assert "archived_count" in data
        assert "not_archived_count" in data

    @pytest.mark.asyncio
    async def test_report_defaults_to_current_month(self, app):
        """Report without year/month params uses current month."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/erp/vendor-invoices/inbound-compliance-report")
        assert resp.status_code == 200
        from datetime import date
        today = date.today()
        assert resp.json()["period"] == f"{today.year:04d}-{today.month:02d}"

    @pytest.mark.asyncio
    async def test_report_sla_compliant_for_empty_month(self, app):
        """Empty month (no received invoices) is SLA compliant by definition."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/erp/vendor-invoices/inbound-compliance-report",
                                    params={"year": 2020, "month": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_invoices_received"] == 0
        assert data["sla_compliant"] is True
        assert data["overdue_fiscalization_count"] == 0


# ── overdue-fiscalizations tests ─────────────────────────────────────────────

class TestOverdueFiscalizations:

    @pytest.mark.asyncio
    async def test_overdue_returns_200_and_list(self, app):
        """overdue-fiscalizations endpoint returns 200 and a list."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/erp/vendor-invoices/overdue-fiscalizations")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_overdue_invoice_has_sla_fields(self, app):
        """An overdue invoice in the list has is_fisc_overdue, fisc_deadline, days_overdue."""
        from services.erp.vendor_invoice_service import get_vendor_invoice_service
        from services.erp.request_context import ERPRequestContext

        # Create an invoice, transition to approved, set received_date to 30 days ago
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_vendor_invoice(client)
            vid = doc["vendor_invoice_id"]
            # → received
            r = await client.post(f"/api/erp/vendor-invoices/{vid}/receive")
            assert r.status_code == 200, f"receive failed: {r.text}"
            # → approved
            r = await client.post(f"/api/erp/vendor-invoices/{vid}/approve")
            assert r.status_code == 200, f"approve failed: {r.text}"

        company = app.dependency_overrides[get_erp_ctx]().company_id
        ctx = ERPRequestContext(
            user_id="test-user", company_id=company,
            role="owner", grants=["*"], denies=[], request_id="x"
        )
        old_date = (date.today() - timedelta(days=30)).isoformat()
        await get_vendor_invoice_service()._get_repo().update(vid, ctx, {"received_date": old_date})

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/erp/vendor-invoices/overdue-fiscalizations")

        assert resp.status_code == 200
        overdues = resp.json()
        # vendor_invoice_id is in _LIST_FIELDS; _id is also present as Firestore doc id
        match = next(
            (d for d in overdues if d.get("vendor_invoice_id") == vid or d.get("_id") == vid),
            None,
        )
        assert match is not None, f"Overdue invoice {vid} not found in response: {overdues}"
        assert match["is_fisc_overdue"] is True
        assert "fisc_deadline" in match
        assert match["days_overdue"] > 0


# ── monitor_drive_invoices auto-archive branch ───────────────────────────────

class TestMonitorAutoArchive:

    @pytest.mark.asyncio
    async def test_archive_drive_document_returns_on_success(self):
        """_archive_drive_document wraps archive_original_document and returns archive_status."""
        from scripts.monitor_drive_invoices import _archive_drive_document
        from services.erp.vendor_invoice_service import VendorInvoiceService

        mock_result = {"vendor_invoice_id": "vi-123", "archive_status": "archived",
                       "archived_at": "2026-03-28T10:00:00+00:00", "drive_folder_id": "folder-abc"}

        with patch.object(VendorInvoiceService, "archive_original_document",
                          new=AsyncMock(return_value=mock_result)):
            result = await _archive_drive_document("vi-123", "drive-file-abc")

        assert result["archive_status"] == "archived"

    @pytest.mark.asyncio
    async def test_archive_drive_document_returns_error_on_failure(self):
        """_archive_drive_document catches exceptions and returns error dict instead of raising."""
        from scripts.monitor_drive_invoices import _archive_drive_document
        from services.erp.vendor_invoice_service import VendorInvoiceService

        with patch.object(VendorInvoiceService, "archive_original_document",
                          new=AsyncMock(side_effect=Exception("Drive timeout"))):
            result = await _archive_drive_document("vi-123", "drive-file-abc")

        assert result["archive_status"] == "error"
        assert "timeout" in result["error"].lower()


# ── Faza 1G/1H gap tests ─────────────────────────────────────────────────────

class TestPendingArchiveRetry:

    @pytest.mark.asyncio
    async def test_pending_archive_returns_200(self, app):
        """GET /pending-archive returns 200 and a list."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/erp/vendor-invoices/pending-archive")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_new_invoice_has_archive_status_not_archived(self, app):
        """Newly created invoice has archive_status=not_archived by default."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_vendor_invoice(client)
        assert doc.get("archive_status") == "not_archived"
        assert doc.get("archive_attempts") == 0

    @pytest.mark.asyncio
    async def test_ocr_invoice_appears_in_pending_archive(self, app):
        """OCR invoice with scan_file_id is included in pending-archive (scan_file_id in _LIST_FIELDS)."""
        from services.erp.vendor_invoice_service import get_vendor_invoice_service
        from services.erp.request_context import ERPRequestContext

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_vendor_invoice(client)
            vid = doc["vendor_invoice_id"]

        ctx = ERPRequestContext(
            user_id="test-user",
            company_id=app.dependency_overrides[get_erp_ctx]().company_id,
            role="owner", grants=["*"], denies=[], request_id="x"
        )
        # Simulate OCR invoice with scan_file_id (no drive_original_file_id)
        await get_vendor_invoice_service()._get_repo().update(vid, ctx, {
            "scan_file_id": "ocr-scan-file-id-123",
            "archive_status": "not_archived",
        })

        pending = await get_vendor_invoice_service().list_pending_archive(ctx)
        match = next((d for d in pending if (d.get("vendor_invoice_id") or d.get("_id")) == vid), None)
        assert match is not None, f"OCR invoice {vid} not found in pending-archive"
        assert match.get("scan_file_id") == "ocr-scan-file-id-123"

    @pytest.mark.asyncio
    async def test_retry_archive_summary_shape(self, app):
        """POST /retry-archive returns summary dict with correct keys."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/erp/vendor-invoices/retry-archive")
        assert resp.status_code == 200
        data = resp.json()
        assert "attempted" in data
        assert "succeeded" in data
        assert "failed" in data
        assert "skipped" in data

    @pytest.mark.asyncio
    async def test_retry_skips_invoice_exceeding_max_retries(self, app):
        """Invoices with archive_attempts >= max_retries are skipped."""
        from services.erp.vendor_invoice_service import get_vendor_invoice_service
        from services.erp.request_context import ERPRequestContext

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            doc = await _create_vendor_invoice(client)
            vid = doc["vendor_invoice_id"]

        ctx = ERPRequestContext(
            user_id="test-user",
            company_id=app.dependency_overrides[get_erp_ctx]().company_id,
            role="owner", grants=["*"], denies=[], request_id="x"
        )
        # Mark as failed with max retries already exhausted
        await get_vendor_invoice_service()._get_repo().update(vid, ctx, {
            "scan_file_id": "some-drive-file",
            "archive_status": "failed",
            "archive_attempts": 99,
        })

        svc = get_vendor_invoice_service()
        summary = await svc.retry_pending_archives(ctx, max_retries=3)
        # The invoice with 99 attempts should be skipped
        assert summary["skipped"] >= 1
        assert summary["attempted"] == 0 or summary.get("skipped", 0) >= 1

    @pytest.mark.asyncio
    async def test_rejected_invoices_returns_200(self, app):
        """GET /rejected returns 200 and a list."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/erp/vendor-invoices/rejected")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestComplianceReportFormats:

    @pytest.mark.asyncio
    async def test_csv_format_returns_text_csv(self, app):
        """format=csv returns Content-Type: text/csv with CSV data."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/erp/vendor-invoices/inbound-compliance-report",
                                    params={"year": 2020, "month": 1, "format": "csv"})
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        assert "Content-Disposition" in resp.headers
        lines = resp.text.splitlines()
        assert len(lines) >= 2  # header + at least one data row

    @pytest.mark.asyncio
    async def test_csv_contains_expected_columns(self, app):
        """CSV header contains expected compliance columns."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/erp/vendor-invoices/inbound-compliance-report",
                                    params={"year": 2020, "month": 1, "format": "csv"})
        header = resp.text.splitlines()[0]
        for col in ("period", "total_invoices_received", "sla_compliant",
                    "overdue_fiscalization_count", "accepted_count", "rejected_count"):
            assert col in header, f"Column '{col}' missing from CSV header"

    @pytest.mark.asyncio
    async def test_json_format_does_not_have_content_disposition(self, app):
        """Default JSON format does NOT set Content-Disposition (not a download)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/erp/vendor-invoices/inbound-compliance-report",
                                    params={"year": 2020, "month": 1})
        assert resp.status_code == 200
        assert "Content-Disposition" not in resp.headers
        assert isinstance(resp.json(), dict)

    @pytest.mark.asyncio
    async def test_csv_and_save_to_drive_both_honoured(self, app):
        """format=csv + save_to_drive=true: Drive upload is attempted AND CSV is returned."""
        from services.erp.vendor_invoice_service import VendorInvoiceService

        mock_drive = AsyncMock(return_value="mock-drive-file-id")

        with patch.object(VendorInvoiceService, "_save_compliance_report_to_drive", new=mock_drive):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get(
                    "/api/erp/vendor-invoices/inbound-compliance-report",
                    params={"year": 2020, "month": 1, "format": "csv", "save_to_drive": "true"},
                )

        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        mock_drive.assert_called_once()  # Drive upload was triggered before CSV return
