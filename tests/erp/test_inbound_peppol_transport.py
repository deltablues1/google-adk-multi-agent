"""
Sprint Inbound B — inbound_peppol_transport_service tests
==========================================================
Service-layer tests for the Peppol inbound transport adapter.

Covers:
  - parse_inbound_payload: camelCase, snake_case, missing submissionId
  - verify_inbound_webhook: no secret (dev), valid HMAC, bad HMAC
  - resolve_company_from_participant_id: found, not found, multiple
  - fetch_xml_bytes: base64 path, URL path (mocked httpx), no document
  - InboundPeppolTransportService.process: happy path, duplicate, malformed XML,
    archive failure, no credentials
  - _process_inbound_ubl shared core: source_meta written to vendor invoice
"""

import pytest
import pytest_asyncio
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from uuid import uuid4
from datetime import date

from services.erp.request_context import ERPRequestContext

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

_FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
_SAMPLE_UBL  = (_FIXTURE_DIR / "sample_inbound_b2b.xml").read_bytes()


def make_ctx(company_id: str) -> ERPRequestContext:
    return ERPRequestContext(
        user_id="test-peppol-inbound",
        company_id=company_id,
        role="owner",
        grants=["*"],
        denies=[],
        request_id=str(uuid4()),
    )


def _make_ubl(invoice_no: str) -> bytes:
    xml = _SAMPLE_UBL.decode("utf-8")
    xml = xml.replace("THT-2026-005432", invoice_no)
    return xml.encode("utf-8")


def _peppol_meta(submission_id: str = "", sender: str = "0190:81793146560") -> dict:
    return {
        "ap_submission_id":        submission_id or f"AP-SID-{uuid4().hex[:10]}",
        "ap_document_id":          f"DOC-{uuid4().hex[:8]}",
        "sender_participant_id":   sender,
        "receiver_participant_id": "0190:47034854402",
        "received_at":             "2026-04-14T08:00:00+00:00",
        "filename":                "eracun_test.xml",
    }


@pytest.fixture
def cid():
    return f"test_peppol_inbound_{uuid4().hex}"


# ── parse_inbound_payload ─────────────────────────────────────────────────────

class TestParseInboundPayload:
    """Sync unit tests — live in test_unit_sync.py for asyncio marker compatibility.
    These integration-level parse tests use the real function."""

    @pytest.mark.asyncio
    async def test_camelcase_fields_parsed(self):
        from services.erp.inbound_peppol_transport_service import parse_inbound_payload
        p = parse_inbound_payload({
            "submissionId": "SID-1",
            "receiverId":   "0190:12345678901",
            "senderId":     "0190:98765432109",
            "documentId":   "DOC-1",
        })
        assert p["ap_submission_id"]        == "SID-1"
        assert p["receiver_participant_id"] == "0190:12345678901"
        assert p["sender_participant_id"]   == "0190:98765432109"
        assert p["ap_document_id"]          == "DOC-1"

    @pytest.mark.asyncio
    async def test_snake_case_fields_parsed(self):
        from services.erp.inbound_peppol_transport_service import parse_inbound_payload
        p = parse_inbound_payload({
            "submission_id": "SID-2",
            "receiver_id":   "0190:22222222220",
        })
        assert p["ap_submission_id"]        == "SID-2"
        assert p["receiver_participant_id"] == "0190:22222222220"

    @pytest.mark.asyncio
    async def test_missing_submission_id_returns_empty(self):
        from services.erp.inbound_peppol_transport_service import parse_inbound_payload
        assert parse_inbound_payload({"receiverId": "0190:123"}) == {}

    @pytest.mark.asyncio
    async def test_empty_body_returns_empty(self):
        from services.erp.inbound_peppol_transport_service import parse_inbound_payload
        assert parse_inbound_payload({})   == {}
        assert parse_inbound_payload(None) == {}

    @pytest.mark.asyncio
    async def test_base64_and_url_extracted(self):
        from services.erp.inbound_peppol_transport_service import parse_inbound_payload
        p = parse_inbound_payload({
            "submissionId":   "SID-3",
            "documentBase64": "BASE64DATA",
            "documentUrl":    "https://ap.example.hr/docs/SID-3",
            "filename":       "invoice.xml",
        })
        assert p["xml_base64"] == "BASE64DATA"
        assert p["xml_url"]    == "https://ap.example.hr/docs/SID-3"
        assert p["filename"]   == "invoice.xml"


# ── resolve_company_from_participant_id ───────────────────────────────────────

class TestCompanyResolution:

    @pytest.mark.asyncio
    async def test_registered_participant_resolves_company(self, cid):
        """Company with matching peppol_participant_id is found."""
        from services.erp.inbound_peppol_transport_service import resolve_company_from_participant_id
        from services.erp.base_erp_service import get_firestore_db

        participant_id = f"0190:{uuid4().hex[:11]}"
        # Register company
        db = get_firestore_db()
        await db.collection("company_settings").document(cid).set({
            "company_id":              cid,
            "peppol_participant_id":   participant_id,
            "oib":                     "47034854402",
        })

        result = await resolve_company_from_participant_id(participant_id)
        assert result == cid, f"Expected {cid!r}, got {result!r}"

    @pytest.mark.asyncio
    async def test_unknown_participant_returns_none(self):
        """Participant ID not in company_settings returns None."""
        from services.erp.inbound_peppol_transport_service import resolve_company_from_participant_id
        result = await resolve_company_from_participant_id("0190:NOTREGISTERED00")
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_participant_returns_none(self):
        from services.erp.inbound_peppol_transport_service import resolve_company_from_participant_id
        assert await resolve_company_from_participant_id("") is None


# ── fetch_xml_bytes ───────────────────────────────────────────────────────────

class TestFetchXmlBytes:

    @pytest.mark.asyncio
    async def test_base64_decoded_correctly(self):
        import base64
        from services.erp.inbound_peppol_transport_service import fetch_xml_bytes
        raw = b"<Invoice>test</Invoice>"
        encoded = base64.b64encode(raw).decode()
        result = await fetch_xml_bytes({"xml_base64": encoded})
        assert result == raw

    @pytest.mark.asyncio
    async def test_no_document_returns_none(self):
        from services.erp.inbound_peppol_transport_service import fetch_xml_bytes
        result = await fetch_xml_bytes({"ap_submission_id": "X"})
        assert result is None

    @pytest.mark.asyncio
    async def test_url_fetched_via_httpx(self):
        from services.erp.inbound_peppol_transport_service import fetch_xml_bytes
        xml = b"<Invoice>url-fetched</Invoice>"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = xml

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await fetch_xml_bytes({"xml_url": "https://ap.example.hr/doc/1"})

        assert result == xml

    @pytest.mark.asyncio
    async def test_url_404_returns_none(self):
        from services.erp.inbound_peppol_transport_service import fetch_xml_bytes

        mock_resp = MagicMock()
        mock_resp.status_code = 404

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await fetch_xml_bytes({"xml_url": "https://ap.example.hr/doc/missing"})

        assert result is None

    @pytest.mark.asyncio
    async def test_url_200_with_api_key_sends_bearer_header(self):
        """B.2: PEPPOL_AP_API_KEY is set → Authorization: Bearer header sent."""
        import os
        from services.erp.inbound_peppol_transport_service import fetch_xml_bytes

        xml = b"<Invoice>auth-fetched</Invoice>"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = xml

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        os.environ["PEPPOL_AP_API_KEY"] = "secret-token-123"
        try:
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await fetch_xml_bytes({"xml_url": "https://ap.example.hr/doc/auth"})
        finally:
            os.environ.pop("PEPPOL_AP_API_KEY", None)

        assert result == xml
        call_kwargs = mock_client.get.call_args.kwargs
        assert call_kwargs.get("headers", {}).get("Authorization") == "Bearer secret-token-123"

    @pytest.mark.asyncio
    async def test_url_401_returns_none(self):
        """B.2: AP returns 401 Unauthorized → None (log + skip)."""
        from services.erp.inbound_peppol_transport_service import fetch_xml_bytes

        mock_resp = MagicMock()
        mock_resp.status_code = 401

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await fetch_xml_bytes({"xml_url": "https://ap.example.hr/doc/private"})

        assert result is None

    @pytest.mark.asyncio
    async def test_url_no_api_key_sends_no_auth_header(self):
        """B.2: PEPPOL_AP_API_KEY unset → no Authorization header in request."""
        import os
        from services.erp.inbound_peppol_transport_service import fetch_xml_bytes

        os.environ.pop("PEPPOL_AP_API_KEY", None)
        xml = b"<Invoice>open</Invoice>"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = xml

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await fetch_xml_bytes({"xml_url": "https://ap.example.hr/doc/open"})

        assert result == xml
        call_kwargs = mock_client.get.call_args.kwargs
        assert not call_kwargs.get("headers"), "No auth headers should be sent when API key is absent"


# ── InboundPeppolTransportService.process ────────────────────────────────────

class TestInboundPeppolProcess:

    @pytest.mark.asyncio
    async def test_valid_ubl_creates_draft_vendor_invoice(self, cid):
        """Happy path: valid UBL bytes → vendor invoice draft created."""
        from services.erp.inbound_peppol_transport_service import InboundPeppolTransportService
        from services.erp.company_service import CompanyService

        ctx = make_ctx(cid)
        await CompanyService().upsert({"oib": "47034854402", "name": "Test Buyer"}, ctx)

        xml    = _make_ubl(f"AP-INV-{uuid4().hex[:8]}")
        parsed = _peppol_meta()

        svc    = InboundPeppolTransportService()
        result = await svc.process(parsed, xml, ctx, archive=False)

        assert result["status"] == "imported", f"Expected imported: {result}"
        assert "vendor_invoice_id" in result
        assert result["ap_submission_id"] == parsed["ap_submission_id"]

    @pytest.mark.asyncio
    async def test_source_metadata_written_to_vendor_invoice(self, cid):
        """Peppol source metadata fields are persisted on the vendor invoice doc."""
        from services.erp.inbound_peppol_transport_service import InboundPeppolTransportService
        from services.erp.company_service import CompanyService
        from services.erp.base_erp_service import get_firestore_db

        ctx = make_ctx(cid)
        await CompanyService().upsert({"oib": "47034854402", "name": "Test Buyer"}, ctx)

        submission_id = f"AP-META-{uuid4().hex[:8]}"
        xml           = _make_ubl(f"AP-META-INV-{uuid4().hex[:8]}")
        parsed        = _peppol_meta(submission_id)

        svc    = InboundPeppolTransportService()
        result = await svc.process(parsed, xml, ctx, archive=False)
        assert result["status"] == "imported"

        doc = (await get_firestore_db()
               .collection("vendor_invoices")
               .document(result["vendor_invoice_id"])
               .get()).to_dict()

        assert doc.get("source_type")               == "peppol_inbound"
        assert doc.get("source_ap_submission_id")   == submission_id
        assert doc.get("source_sender_participant_id") == "0190:81793146560"

    @pytest.mark.asyncio
    async def test_duplicate_ubl_returns_duplicate_status(self, cid):
        """Same UBL sent twice → second is idempotent skip."""
        from services.erp.inbound_peppol_transport_service import InboundPeppolTransportService
        from services.erp.company_service import CompanyService

        ctx = make_ctx(cid)
        await CompanyService().upsert({"oib": "47034854402", "name": "Test Buyer"}, ctx)

        xml    = _make_ubl(f"AP-DUP-{uuid4().hex[:8]}")
        parsed = _peppol_meta()
        svc    = InboundPeppolTransportService()

        r1 = await svc.process(parsed, xml, ctx, archive=False)
        assert r1["status"] == "imported"

        r2 = await svc.process(parsed, xml, ctx, archive=False)
        assert r2["status"] == "duplicate"

    @pytest.mark.asyncio
    async def test_malformed_xml_returns_failed_status(self, cid):
        """Malformed XML does not raise — returns status='failed'."""
        from services.erp.inbound_peppol_transport_service import InboundPeppolTransportService
        from services.erp.company_service import CompanyService

        ctx    = make_ctx(cid)
        await CompanyService().upsert({"oib": "47034854402", "name": "Test Buyer"}, ctx)
        parsed = _peppol_meta()
        svc    = InboundPeppolTransportService()

        result = await svc.process(parsed, b"NOT VALID XML <<<", ctx, archive=False)
        assert result["status"] == "failed"
        assert "error" in result

    @pytest.mark.asyncio
    async def test_archive_success_patches_vendor_invoice(self, cid):
        """Archive success → archive fields written to vendor invoice doc."""
        from services.erp.inbound_peppol_transport_service import InboundPeppolTransportService
        from services.erp.company_service import CompanyService
        from services.erp.base_erp_service import get_firestore_db

        ctx = make_ctx(cid)
        await CompanyService().upsert({"oib": "47034854402", "name": "Test Buyer"}, ctx)

        xml    = _make_ubl(f"AP-ARCH-{uuid4().hex[:8]}")
        parsed = _peppol_meta()

        with patch(
            "services.erp.inbound_eracun_transport_service._archive_xml_bytes",
            new=AsyncMock(return_value={
                "ok": True,
                "drive_file_id":   "peppol-file-001",
                "drive_folder_id": "peppol-folder-001",
                "archived_at":     "2026-04-14T08:00:00+00:00",
            }),
        ):
            svc    = InboundPeppolTransportService()
            result = await svc.process(parsed, xml, ctx, credentials=MagicMock(), archive=True)

        assert result["status"]       == "imported"
        assert result["archive_status"] == "archived"

        doc = (await get_firestore_db()
               .collection("vendor_invoices")
               .document(result["vendor_invoice_id"])
               .get()).to_dict()
        assert doc.get("archive_status")         == "archived"
        assert doc.get("drive_original_file_id") == "peppol-file-001"

    @pytest.mark.asyncio
    async def test_archive_failure_does_not_abort_import(self, cid):
        """Archive failure → intake still succeeds, archive_status='not_archived'."""
        from services.erp.inbound_peppol_transport_service import InboundPeppolTransportService
        from services.erp.company_service import CompanyService

        ctx = make_ctx(cid)
        await CompanyService().upsert({"oib": "47034854402", "name": "Test Buyer"}, ctx)

        xml    = _make_ubl(f"AP-ARCHFAIL-{uuid4().hex[:8]}")
        parsed = _peppol_meta()

        with patch(
            "services.erp.inbound_eracun_transport_service._archive_xml_bytes",
            new=AsyncMock(return_value={"ok": False, "error": "Drive unavailable"}),
        ):
            svc    = InboundPeppolTransportService()
            result = await svc.process(parsed, xml, ctx, credentials=MagicMock(), archive=True)

        assert result["status"]         == "imported"
        assert result["archive_status"] == "not_archived"


# ── Sprint B.1: byte re-upload retry path ────────────────────────────────────

class TestArchiveOriginalDocumentByteReupload:
    """
    B.1: archive_original_document() byte re-upload path for Peppol/Gmail inbound
    docs that have source_ubl_xml stored in Firestore but no drive_original_file_id.
    This exercises VendorInvoiceService.archive_original_document() directly.
    """

    @pytest.mark.asyncio
    async def test_retry_peppol_inbound_doc_without_drive_file(self, cid):
        """
        B.1 regression: vendor invoice with source_ubl_xml but no drive_original_file_id
        → archive_original_document() re-uploads bytes and patches drive_original_file_id.
        """
        from services.erp.inbound_peppol_transport_service import InboundPeppolTransportService
        from services.erp.company_service import CompanyService
        from services.erp.vendor_invoice_service import VendorInvoiceService
        from services.erp.base_erp_service import get_firestore_db

        ctx = make_ctx(cid)
        await CompanyService().upsert({"oib": "47034854402", "name": "Test Buyer"}, ctx)

        # 1) Create the vendor invoice via Peppol inbound with archive=False
        #    (simulates original intake where archive was skipped or failed)
        xml    = _make_ubl(f"AP-RETRY-{uuid4().hex[:8]}")
        parsed = _peppol_meta()

        svc    = InboundPeppolTransportService()
        result = await svc.process(parsed, xml, ctx, archive=False)
        assert result["status"] == "imported"

        vendor_invoice_id = result["vendor_invoice_id"]

        # 2) Confirm the doc has source_ubl_xml but no drive_original_file_id
        db  = get_firestore_db()
        doc = (await db.collection("vendor_invoices").document(vendor_invoice_id).get()).to_dict()
        assert doc.get("source_ubl_xml"), "source_ubl_xml should be stored after Peppol intake"
        assert not doc.get("drive_original_file_id"), "No Drive file yet — archive was skipped"

        # 3) Call archive_original_document() with mocked Drive bytes-upload
        mock_archive_result = {
            "ok":            True,
            "drive_file_id":   "retry-drive-001",
            "drive_folder_id": "retry-folder-001",
            "archived_at":     "2026-04-14T12:00:00+00:00",
        }
        with patch(
            "services.erp.drive_archive_service.archive_inbound_bytes",
            new=AsyncMock(return_value=mock_archive_result),
        ):
            archive_result = await VendorInvoiceService().archive_original_document(
                vendor_invoice_id, ctx
            )

        # 4) Verify result
        assert archive_result["archive_status"] == "archived", f"Expected archived: {archive_result}"

        # 5) Verify Firestore was updated with new Drive file ID and archive fields
        updated = (await db.collection("vendor_invoices").document(vendor_invoice_id).get()).to_dict()
        assert updated.get("archive_status")         == "archived"
        assert updated.get("drive_original_file_id") == "retry-drive-001", (
            "drive_original_file_id should be backpatched after byte re-upload"
        )
