"""
Sprint Inbound A — inbound_eracun_transport_service tests
==========================================================
Integration tests for Gmail UBL/XML attachment intake path.

Covers:
  - Gmail XML attachment → vendor invoice draft created
  - Duplicate UBL → idempotent skip, no second invoice, no 500
  - Archive bytes success → archive metadata written to vendor invoice
  - Archive failure → intake succeeds, status is "not_archived"
  - Malformed XML → controlled failure, audit written, no exception raised
  - Non-XML attachment → _is_ubl_attachment returns False (unit-level)
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

# Unique vendor invoice no so each test run uses a fresh UBL
# (dedup is based on vendor_oib + invoice_no + date + amount)


def make_ctx(company_id: str) -> ERPRequestContext:
    return ERPRequestContext(
        user_id="test-inbound",
        company_id=company_id,
        role="owner",
        grants=["*"],
        denies=[],
        request_id=str(uuid4()),
    )


def _make_ubl(invoice_no: str) -> bytes:
    """Return sample UBL with a unique invoice number to avoid cross-test dedup collisions."""
    xml = _SAMPLE_UBL.decode("utf-8")
    xml = xml.replace("THT-2026-005432", invoice_no)
    return xml.encode("utf-8")


def _message_meta(msg_id: str = "") -> dict:
    return {
        "message_id":  msg_id or f"gmail-msg-{uuid4().hex[:10]}",
        "thread_id":   f"gmail-thread-{uuid4().hex[:10]}",
        "from":        "dobavljac@example.hr",
        "subject":     "eRačun travanj 2026",
        "received_at": "2026-04-13T09:00:00+00:00",
    }


@pytest.fixture
def cid():
    return f"test_inbound_{uuid4().hex}"


# ── Gmail XML attachment → vendor invoice draft created ───────────────────────

class TestGmailImport:

    @pytest.mark.asyncio
    async def test_xml_attachment_creates_draft_vendor_invoice(self, cid):
        """process_gmail_ubl_attachment() creates a draft vendor invoice from valid UBL."""
        from services.erp.inbound_eracun_transport_service import InboundEracunTransportService
        from services.erp.company_service import CompanyService

        ctx = make_ctx(cid)
        # Register our company OIB so buyer validation passes
        await CompanyService().upsert({"oib": "47034854402", "name": "Test Kupac"}, ctx)

        xml = _make_ubl(f"INV-{uuid4().hex[:8]}")
        svc = InboundEracunTransportService()

        result = await svc.process_gmail_ubl_attachment(
            credentials=None,
            message_meta=_message_meta(),
            attachment_name="eracun.xml",
            xml_bytes=xml,
            ctx=ctx,
            archive=False,   # no Drive in tests
        )

        assert result["status"] == "imported", f"Expected imported, got: {result}"
        assert "vendor_invoice_id" in result
        assert result["attachment_name"] == "eracun.xml"
        assert result["archive_status"] == "skipped"   # archive=False

    @pytest.mark.asyncio
    async def test_source_metadata_written_to_vendor_invoice(self, cid):
        """Source metadata fields are written to the vendor invoice document."""
        from services.erp.inbound_eracun_transport_service import InboundEracunTransportService
        from services.erp.company_service import CompanyService
        from services.erp.base_erp_service import get_firestore_db

        ctx = make_ctx(cid)
        await CompanyService().upsert({"oib": "47034854402", "name": "Test Kupac"}, ctx)

        msg_id = f"msg-{uuid4().hex[:10]}"
        meta = _message_meta(msg_id)
        xml  = _make_ubl(f"INV-{uuid4().hex[:8]}")

        svc = InboundEracunTransportService()
        result = await svc.process_gmail_ubl_attachment(
            credentials=None,
            message_meta=meta,
            attachment_name="racun_test.xml",
            xml_bytes=xml,
            ctx=ctx,
            archive=False,
        )
        assert result["status"] == "imported"

        doc = (await get_firestore_db()
               .collection("vendor_invoices")
               .document(result["vendor_invoice_id"])
               .get()).to_dict()

        assert doc.get("source_type") == "gmail_attachment"
        assert doc.get("source_email_message_id") == msg_id
        assert doc.get("source_email_from") == "dobavljac@example.hr"
        assert doc.get("source_email_attachment_name") == "racun_test.xml"

    @pytest.mark.asyncio
    async def test_archive_success_patches_vendor_invoice(self, cid):
        """When archive succeeds, archive fields are written back to the vendor invoice."""
        from services.erp.inbound_eracun_transport_service import InboundEracunTransportService
        from services.erp.company_service import CompanyService
        from services.erp.base_erp_service import get_firestore_db

        ctx = make_ctx(cid)
        await CompanyService().upsert({"oib": "47034854402", "name": "Test Kupac"}, ctx)

        xml = _make_ubl(f"INV-{uuid4().hex[:8]}")
        fake_credentials = MagicMock()

        with patch(
            "services.erp.inbound_eracun_transport_service._archive_xml_bytes",
            new=AsyncMock(return_value={
                "ok": True,
                "drive_file_id": "fake-drive-id-001",
                "drive_folder_id": "fake-folder-id",
                "archived_at": "2026-04-13T10:00:00+00:00",
            }),
        ):
            svc = InboundEracunTransportService()
            result = await svc.process_gmail_ubl_attachment(
                credentials=fake_credentials,
                message_meta=_message_meta(),
                attachment_name="eracun_arch.xml",
                xml_bytes=xml,
                ctx=ctx,
                archive=True,
            )

        assert result["status"] == "imported"
        assert result["archive_status"] == "archived"
        assert result["drive_file_id"] == "fake-drive-id-001"

        doc = (await get_firestore_db()
               .collection("vendor_invoices")
               .document(result["vendor_invoice_id"])
               .get()).to_dict()

        assert doc.get("archive_status") == "archived"
        assert doc.get("drive_original_file_id") == "fake-drive-id-001"

    @pytest.mark.asyncio
    async def test_archive_failure_returns_not_archived_status(self, cid):
        """Archive failure does not abort intake — status is 'not_archived', invoice still created."""
        from services.erp.inbound_eracun_transport_service import InboundEracunTransportService
        from services.erp.company_service import CompanyService

        ctx = make_ctx(cid)
        await CompanyService().upsert({"oib": "47034854402", "name": "Test Kupac"}, ctx)

        xml = _make_ubl(f"INV-{uuid4().hex[:8]}")
        fake_credentials = MagicMock()

        with patch(
            "services.erp.inbound_eracun_transport_service._archive_xml_bytes",
            new=AsyncMock(return_value={"ok": False, "error": "Drive unreachable"}),
        ):
            svc = InboundEracunTransportService()
            result = await svc.process_gmail_ubl_attachment(
                credentials=fake_credentials,
                message_meta=_message_meta(),
                attachment_name="eracun_fail.xml",
                xml_bytes=xml,
                ctx=ctx,
                archive=True,
            )

        assert result["status"] == "imported", "Intake must succeed even when archive fails"
        assert result["archive_status"] == "not_archived"


# ── Duplicate UBL → idempotent skip ──────────────────────────────────────────

class TestDuplicateHandling:

    @pytest.mark.asyncio
    async def test_duplicate_ubl_returns_duplicate_status(self, cid):
        """Sending the same UBL twice returns status='duplicate' on second call."""
        from services.erp.inbound_eracun_transport_service import InboundEracunTransportService
        from services.erp.company_service import CompanyService

        ctx = make_ctx(cid)
        await CompanyService().upsert({"oib": "47034854402", "name": "Test Kupac"}, ctx)

        xml = _make_ubl(f"INV-DEDUP-{uuid4().hex[:8]}")
        svc = InboundEracunTransportService()

        r1 = await svc.process_gmail_ubl_attachment(
            credentials=None,
            message_meta=_message_meta(),
            attachment_name="first.xml",
            xml_bytes=xml, ctx=ctx, archive=False,
        )
        assert r1["status"] == "imported"

        r2 = await svc.process_gmail_ubl_attachment(
            credentials=None,
            message_meta=_message_meta(),
            attachment_name="first.xml",
            xml_bytes=xml, ctx=ctx, archive=False,
        )
        assert r2["status"] == "duplicate", "Second identical UBL must be idempotent skip"

    @pytest.mark.asyncio
    async def test_duplicate_does_not_create_second_invoice(self, cid):
        """After a duplicate skip, exactly one vendor invoice exists for that supplier+no+date."""
        from services.erp.inbound_eracun_transport_service import InboundEracunTransportService
        from services.erp.company_service import CompanyService
        from services.erp.base_erp_service import get_firestore_db
        from google.cloud.firestore_v1.base_query import FieldFilter

        ctx = make_ctx(cid)
        await CompanyService().upsert({"oib": "47034854402", "name": "Test Kupac"}, ctx)

        inv_no = f"INV-ONCE-{uuid4().hex[:8]}"
        xml = _make_ubl(inv_no)
        svc = InboundEracunTransportService()

        await svc.process_gmail_ubl_attachment(
            credentials=None, message_meta=_message_meta(),
            attachment_name="once.xml", xml_bytes=xml, ctx=ctx, archive=False,
        )
        await svc.process_gmail_ubl_attachment(
            credentials=None, message_meta=_message_meta(),
            attachment_name="once.xml", xml_bytes=xml, ctx=ctx, archive=False,
        )

        db = get_firestore_db()
        snaps = [
            snap async for snap in
            db.collection("vendor_invoices")
            .where(filter=FieldFilter("company_id", "==", cid))
            .where(filter=FieldFilter("vendor_invoice_no", "==", inv_no))
            .stream()
        ]
        assert len(snaps) == 1, "Exactly one vendor invoice must exist after duplicate skip"


# ── Malformed XML → controlled failure ───────────────────────────────────────

class TestMalformedXml:

    @pytest.mark.asyncio
    async def test_malformed_xml_returns_failed_status(self, cid):
        """Malformed XML does not raise — returns status='failed' with error message."""
        from services.erp.inbound_eracun_transport_service import InboundEracunTransportService
        from services.erp.company_service import CompanyService

        ctx = make_ctx(cid)
        await CompanyService().upsert({"oib": "47034854402", "name": "Test Kupac"}, ctx)

        svc = InboundEracunTransportService()
        result = await svc.process_gmail_ubl_attachment(
            credentials=None,
            message_meta=_message_meta(),
            attachment_name="corrupt.xml",
            xml_bytes=b"NOT VALID XML <<<",
            ctx=ctx,
            archive=False,
        )

        assert result["status"] == "failed"
        assert "error" in result
        assert result["archive_status"] == "skipped"

    @pytest.mark.asyncio
    async def test_empty_bytes_returns_failed_status(self, cid):
        """Empty XML bytes return status='failed'."""
        from services.erp.inbound_eracun_transport_service import InboundEracunTransportService
        from services.erp.company_service import CompanyService

        ctx = make_ctx(cid)
        await CompanyService().upsert({"oib": "47034854402", "name": "Test Kupac"}, ctx)

        svc = InboundEracunTransportService()
        result = await svc.process_gmail_ubl_attachment(
            credentials=None,
            message_meta=_message_meta(),
            attachment_name="empty.xml",
            xml_bytes=b"",
            ctx=ctx,
            archive=False,
        )
        assert result["status"] == "failed"


# ── Attachment filter and Gmail helper unit tests live in test_unit_sync.py ───
# (Moved to avoid asyncio marker warnings on sync test functions.)


# ── Sprint Inbound A.1 — poll_gmail_inbound() batch path ─────────────────────

def _make_stub(msg_id: str, thread_id: str = "") -> dict:
    return {"id": msg_id, "thread_id": thread_id or f"thread-{msg_id}"}


def _make_full_msg(msg_id: str, attachments: list, *, from_: str = "x@y.hr") -> dict:
    return {
        "id":          msg_id,
        "thread_id":   f"thread-{msg_id}",
        "from":        from_,
        "subject":     "eRačun test",
        "received_at": "2026-04-13T09:00:00+00:00",
        "snippet":     "",
        "attachments": attachments,
    }


def _xml_att(att_id: str, filename: str = "invoice.xml") -> dict:
    return {"attachment_id": att_id, "filename": filename, "mime_type": "application/xml", "size": 1024}


def _pdf_att(att_id: str) -> dict:
    return {"attachment_id": att_id, "filename": "attachment.pdf", "mime_type": "application/pdf", "size": 2048}


class TestPollGmailInbound:
    """
    Batch poll path tests — all Gmail API calls are mocked.
    Tests verify:
      - label ID resolution (not label name) via gmail_get_or_create_label
      - message-level (not thread-level) gmail_modify_message called
      - correct summary counts returned
      - second message in same thread is processed independently
    """

    @pytest.mark.asyncio
    async def test_poll_all_imported_calls_modify_message(self, cid):
        """
        When all messages are new valid UBL, poll returns imported count and
        gmail_modify_message is called with label ID (not name) for each message.
        """
        from services.erp.inbound_eracun_transport_service import InboundEracunTransportService
        from services.erp.company_service import CompanyService

        ctx = make_ctx(cid)
        await CompanyService().upsert({"oib": "47034854402", "name": "Test"}, ctx)

        msg_id  = f"msg-{uuid4().hex[:8]}"
        xml     = _make_ubl(f"INV-POLL-{uuid4().hex[:8]}")
        label_id = "Label_ERP_IMPORTED_ID"

        with (
            patch("tools.api_implementations.gmail_api.gmail_list_messages_with_attachments",
                  new=AsyncMock(return_value={"messages": [_make_stub(msg_id)], "result_size_estimate": 1, "query": ""})),
            patch("tools.api_implementations.gmail_api.gmail_get_message_full",
                  new=AsyncMock(return_value=_make_full_msg(msg_id, [_xml_att("att-1")]))),
            patch("tools.api_implementations.gmail_api.gmail_download_attachment",
                  new=AsyncMock(return_value=xml)),
            patch("tools.api_implementations.gmail_api.gmail_get_or_create_label",
                  new=AsyncMock(return_value=label_id)) as mock_label,
            patch("tools.api_implementations.gmail_api.gmail_modify_message",
                  new=AsyncMock()) as mock_modify,
            patch("services.erp.inbound_eracun_transport_service._archive_xml_bytes",
                  new=AsyncMock(return_value={"ok": False, "error": "test-no-drive"})),
        ):
            svc = InboundEracunTransportService()
            summary = await svc.poll_gmail_inbound(
                credentials=object(),  # non-None sentinel
                ctx=ctx,
            )

        assert summary["imported"] == 1
        assert summary["failed"]   == 0
        assert summary["skipped"]  == 0

        # Label resolved by name (not raw string passed directly)
        assert mock_label.call_count == 1
        assert mock_label.call_args.args[1] == "ERP_IMPORTED"   # second arg is label_name
        # modify_message called with resolved label ID, not the raw label name
        mock_modify.assert_called_once()
        modify_kwargs = mock_modify.call_args.kwargs
        assert modify_kwargs.get("add_label_ids") == [label_id]

    @pytest.mark.asyncio
    async def test_poll_duplicate_message_gets_duplicate_label(self, cid):
        """Already-processed UBL gives summary duplicate=1 and ERP_DUPLICATE label is applied."""
        from services.erp.inbound_eracun_transport_service import InboundEracunTransportService
        from services.erp.company_service import CompanyService

        ctx = make_ctx(cid)
        await CompanyService().upsert({"oib": "47034854402", "name": "Test"}, ctx)

        # Pre-create invoice so second attempt is duplicate
        inv_no = f"INV-DUP-POLL-{uuid4().hex[:8]}"
        xml = _make_ubl(inv_no)
        from services.erp.inbound_eracun_transport_service import InboundEracunTransportService as S
        await S().process_gmail_ubl_attachment(
            credentials=None, message_meta=_message_meta(),
            attachment_name="first.xml", xml_bytes=xml, ctx=ctx, archive=False,
        )

        msg_id   = f"msg-{uuid4().hex[:8]}"
        dup_label_id = "Label_ERP_DUPLICATE_ID"

        with (
            patch("tools.api_implementations.gmail_api.gmail_list_messages_with_attachments",
                  new=AsyncMock(return_value={"messages": [_make_stub(msg_id)], "result_size_estimate": 1, "query": ""})),
            patch("tools.api_implementations.gmail_api.gmail_get_message_full",
                  new=AsyncMock(return_value=_make_full_msg(msg_id, [_xml_att("att-dup")]))),
            patch("tools.api_implementations.gmail_api.gmail_download_attachment",
                  new=AsyncMock(return_value=xml)),
            patch("tools.api_implementations.gmail_api.gmail_get_or_create_label",
                  new=AsyncMock(return_value=dup_label_id)),
            patch("tools.api_implementations.gmail_api.gmail_modify_message",
                  new=AsyncMock()) as mock_modify,
        ):
            svc = InboundEracunTransportService()
            summary = await svc.poll_gmail_inbound(credentials=object(), ctx=ctx)

        assert summary["duplicate"] == 1
        assert summary["imported"]  == 0
        mock_modify.assert_called_once()

    @pytest.mark.asyncio
    async def test_poll_no_xml_attachment_skipped(self, cid):
        """Message with only PDF attachment is skipped — no vendor invoice, no label."""
        from services.erp.inbound_eracun_transport_service import InboundEracunTransportService
        from services.erp.company_service import CompanyService

        ctx = make_ctx(cid)
        await CompanyService().upsert({"oib": "47034854402", "name": "Test"}, ctx)

        msg_id = f"msg-{uuid4().hex[:8]}"

        with (
            patch("tools.api_implementations.gmail_api.gmail_list_messages_with_attachments",
                  new=AsyncMock(return_value={"messages": [_make_stub(msg_id)], "result_size_estimate": 1, "query": ""})),
            patch("tools.api_implementations.gmail_api.gmail_get_message_full",
                  new=AsyncMock(return_value=_make_full_msg(msg_id, [_pdf_att("att-pdf")]))),
            patch("tools.api_implementations.gmail_api.gmail_modify_message",
                  new=AsyncMock()) as mock_modify,
        ):
            svc = InboundEracunTransportService()
            summary = await svc.poll_gmail_inbound(credentials=object(), ctx=ctx)

        assert summary["skipped"]  == 1
        assert summary["imported"] == 0
        mock_modify.assert_not_called()   # no label on skipped messages

    @pytest.mark.asyncio
    async def test_poll_failed_fetch_counted_as_failed(self, cid):
        """When gmail_get_message_full raises, message is counted as failed."""
        from services.erp.inbound_eracun_transport_service import InboundEracunTransportService
        from services.erp.company_service import CompanyService

        ctx = make_ctx(cid)
        await CompanyService().upsert({"oib": "47034854402", "name": "Test"}, ctx)

        msg_id = f"msg-{uuid4().hex[:8]}"

        with (
            patch("tools.api_implementations.gmail_api.gmail_list_messages_with_attachments",
                  new=AsyncMock(return_value={"messages": [_make_stub(msg_id)], "result_size_estimate": 1, "query": ""})),
            patch("tools.api_implementations.gmail_api.gmail_get_message_full",
                  new=AsyncMock(side_effect=Exception("network timeout"))),
            patch("tools.api_implementations.gmail_api.gmail_modify_message",
                  new=AsyncMock()) as mock_modify,
        ):
            svc = InboundEracunTransportService()
            summary = await svc.poll_gmail_inbound(credentials=object(), ctx=ctx)

        assert summary["failed"] == 1
        mock_modify.assert_not_called()   # fetch failed before we could label

    @pytest.mark.asyncio
    async def test_poll_two_messages_same_thread_both_processed(self, cid):
        """
        Two messages in the same thread are processed independently.
        Message-level labeling means the second message is still discovered
        even though the first was already labeled.
        """
        from services.erp.inbound_eracun_transport_service import InboundEracunTransportService
        from services.erp.company_service import CompanyService

        ctx = make_ctx(cid)
        await CompanyService().upsert({"oib": "47034854402", "name": "Test"}, ctx)

        thread_id = f"thread-{uuid4().hex[:8]}"
        msg_id_1  = f"msg-A-{uuid4().hex[:8]}"
        msg_id_2  = f"msg-B-{uuid4().hex[:8]}"
        xml_1 = _make_ubl(f"INV-T1-{uuid4().hex[:8]}")
        xml_2 = _make_ubl(f"INV-T2-{uuid4().hex[:8]}")

        full_msgs = {
            msg_id_1: _make_full_msg(msg_id_1, [_xml_att("att-A")]),
            msg_id_2: _make_full_msg(msg_id_2, [_xml_att("att-B")]),
        }
        att_bytes = {"att-A": xml_1, "att-B": xml_2}

        async def _get_full(creds, mid):
            return full_msgs[mid]

        async def _download(creds, mid, att_id):
            return att_bytes[att_id]

        label_id = "Label_IMPORTED_XYZ"

        with (
            patch("tools.api_implementations.gmail_api.gmail_list_messages_with_attachments",
                  new=AsyncMock(return_value={
                      "messages": [_make_stub(msg_id_1, thread_id), _make_stub(msg_id_2, thread_id)],
                      "result_size_estimate": 2, "query": "",
                  })),
            patch("tools.api_implementations.gmail_api.gmail_get_message_full", new=AsyncMock(side_effect=_get_full)),
            patch("tools.api_implementations.gmail_api.gmail_download_attachment", new=AsyncMock(side_effect=_download)),
            patch("tools.api_implementations.gmail_api.gmail_get_or_create_label", new=AsyncMock(return_value=label_id)),
            patch("tools.api_implementations.gmail_api.gmail_modify_message", new=AsyncMock()) as mock_modify,
        ):
            svc = InboundEracunTransportService()
            summary = await svc.poll_gmail_inbound(credentials=object(), ctx=ctx)

        assert summary["imported"] == 2, "Both messages must be imported independently"
        # modify_message called twice — once per message, not once per thread
        assert mock_modify.call_count == 2
        # Each call targets its own message_id
        called_msg_ids = {call.args[1] for call in mock_modify.call_args_list}
        assert msg_id_1 in called_msg_ids
        assert msg_id_2 in called_msg_ids

    @pytest.mark.asyncio
    async def test_poll_mixed_batch_correct_summary(self, cid):
        """Mixed batch: 1 new + 1 duplicate → summary imported=1, duplicate=1."""
        from services.erp.inbound_eracun_transport_service import InboundEracunTransportService
        from services.erp.company_service import CompanyService

        ctx = make_ctx(cid)
        await CompanyService().upsert({"oib": "47034854402", "name": "Test"}, ctx)

        # Pre-create first invoice
        inv_no_dup = f"INV-MIX-DUP-{uuid4().hex[:8]}"
        xml_dup = _make_ubl(inv_no_dup)
        await InboundEracunTransportService().process_gmail_ubl_attachment(
            credentials=None, message_meta=_message_meta(),
            attachment_name="dup.xml", xml_bytes=xml_dup, ctx=ctx, archive=False,
        )

        xml_new  = _make_ubl(f"INV-MIX-NEW-{uuid4().hex[:8]}")
        msg_dup  = f"msg-dup-{uuid4().hex[:8]}"
        msg_new  = f"msg-new-{uuid4().hex[:8]}"

        full_msgs = {
            msg_dup: _make_full_msg(msg_dup, [_xml_att("att-dup")]),
            msg_new: _make_full_msg(msg_new, [_xml_att("att-new")]),
        }
        att_bytes = {"att-dup": xml_dup, "att-new": xml_new}

        async def _get_full(creds, mid):
            return full_msgs[mid]

        async def _download(creds, mid, att_id):
            return att_bytes[att_id]

        with (
            patch("tools.api_implementations.gmail_api.gmail_list_messages_with_attachments",
                  new=AsyncMock(return_value={
                      "messages": [_make_stub(msg_dup), _make_stub(msg_new)],
                      "result_size_estimate": 2, "query": "",
                  })),
            patch("tools.api_implementations.gmail_api.gmail_get_message_full", new=AsyncMock(side_effect=_get_full)),
            patch("tools.api_implementations.gmail_api.gmail_download_attachment", new=AsyncMock(side_effect=_download)),
            patch("tools.api_implementations.gmail_api.gmail_get_or_create_label", new=AsyncMock(side_effect=lambda c, n: f"LBL_{n}")),
            patch("tools.api_implementations.gmail_api.gmail_modify_message", new=AsyncMock()),
        ):
            svc = InboundEracunTransportService()
            summary = await svc.poll_gmail_inbound(credentials=object(), ctx=ctx)

        assert summary["imported"]  == 1
        assert summary["duplicate"] == 1
        assert summary["failed"]    == 0
