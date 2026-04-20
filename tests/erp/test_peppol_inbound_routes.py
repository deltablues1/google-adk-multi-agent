"""
Sprint Inbound B — Peppol inbound API route tests
==================================================
HTTP-level tests for POST /api/erp/inbound-eracun/peppol/webhook.

Covers:
  - happy path: valid UBL via documentBase64 → 200 imported
  - duplicate UBL → 200 duplicate (idempotent, not 500)
  - malformed XML → 200 failed (intake error, not HTTP error)
  - missing submissionId → 400
  - no document (no base64/url) → 400
  - invalid HMAC signature → 403
  - unknown receiver participant_id → 404
  - multi-company routing via receiver_participant_id
"""

import base64
import json
import pytest
import pytest_asyncio
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import AsyncClient, ASGITransport

from services.erp.request_context import ERPRequestContext
from services.erp.errors import BusinessError

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

_FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
_SAMPLE_UBL  = (_FIXTURE_DIR / "sample_inbound_b2b.xml").read_bytes()


def _make_ubl(invoice_no: str) -> bytes:
    xml = _SAMPLE_UBL.decode("utf-8")
    xml = xml.replace("THT-2026-005432", invoice_no)
    return xml.encode("utf-8")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


@pytest_asyncio.fixture
async def app():
    from web.erp_routes import router as erp_router
    _app = FastAPI()
    _app.exception_handler(BusinessError)(
        lambda req, exc: JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message},
        )
    )
    _app.include_router(erp_router)
    return _app


@pytest.fixture
def cid():
    return f"test_peppol_inbound_route_{uuid4().hex}"


def _payload(
    submission_id: str = "",
    receiver_id: str = "0190:47034854402",
    xml: bytes = b"",
    sender_id: str = "0190:81793146560",
    **extra,
) -> bytes:
    body = {
        "submissionId":   submission_id or f"AP-{uuid4().hex[:10]}",
        "receiverId":     receiver_id,
        "senderId":       sender_id,
        "documentBase64": _b64(xml) if xml else "",
        **extra,
    }
    if not xml and "documentBase64" not in extra:
        body.pop("documentBase64", None)
    return json.dumps(body).encode()


# ── Happy path ────────────────────────────────────────────────────────────────

class TestPeppolInboundWebhookRoute:

    @pytest.mark.asyncio
    async def test_valid_ubl_returns_200_imported(self, app, cid):
        """Valid UBL via base64 → 200 with status=imported."""
        from services.erp.company_service import CompanyService

        ctx = ERPRequestContext(
            user_id="test", company_id=cid, role="owner",
            grants=["*"], denies=[], request_id=str(uuid4()),
        )
        await CompanyService().upsert({"oib": "47034854402", "name": "Test Buyer"}, ctx)

        xml = _make_ubl(f"ROUTE-{uuid4().hex[:8]}")
        import os; os.environ.pop("PEPPOL_AP_INBOUND_WEBHOOK_SECRET", None)
        os.environ.pop("PEPPOL_AP_WEBHOOK_SECRET", None)

        with patch(
            "services.erp.inbound_peppol_transport_service.resolve_company_from_participant_id",
            new=AsyncMock(return_value=cid),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/erp/inbound-eracun/peppol/webhook",
                    content=_payload(xml=xml),
                    headers={"Content-Type": "application/json"},
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"]     is True
        assert body["status"] == "imported"
        assert body["vendor_invoice_id"]

    @pytest.mark.asyncio
    async def test_duplicate_ubl_returns_200_duplicate(self, app, cid):
        """Same UBL sent twice → second returns 200 with status=duplicate."""
        from services.erp.company_service import CompanyService

        ctx = ERPRequestContext(
            user_id="test", company_id=cid, role="owner",
            grants=["*"], denies=[], request_id=str(uuid4()),
        )
        await CompanyService().upsert({"oib": "47034854402", "name": "Test Buyer"}, ctx)

        xml     = _make_ubl(f"ROUTE-DUP-{uuid4().hex[:8]}")
        payload = _payload(xml=xml)
        import os; os.environ.pop("PEPPOL_AP_INBOUND_WEBHOOK_SECRET", None)
        os.environ.pop("PEPPOL_AP_WEBHOOK_SECRET", None)

        with patch(
            "services.erp.inbound_peppol_transport_service.resolve_company_from_participant_id",
            new=AsyncMock(return_value=cid),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                r1 = await client.post(
                    "/api/erp/inbound-eracun/peppol/webhook",
                    content=payload, headers={"Content-Type": "application/json"},
                )
                r2 = await client.post(
                    "/api/erp/inbound-eracun/peppol/webhook",
                    content=payload, headers={"Content-Type": "application/json"},
                )

        assert r1.json()["status"] == "imported"
        assert r2.status_code == 200
        assert r2.json()["status"] == "duplicate"

    @pytest.mark.asyncio
    async def test_malformed_xml_returns_200_failed(self, app, cid):
        """Malformed XML → 200 with status=failed (intake error, not HTTP 500)."""
        from services.erp.company_service import CompanyService

        ctx = ERPRequestContext(
            user_id="test", company_id=cid, role="owner",
            grants=["*"], denies=[], request_id=str(uuid4()),
        )
        await CompanyService().upsert({"oib": "47034854402", "name": "Test Buyer"}, ctx)

        import os; os.environ.pop("PEPPOL_AP_INBOUND_WEBHOOK_SECRET", None)
        os.environ.pop("PEPPOL_AP_WEBHOOK_SECRET", None)

        with patch(
            "services.erp.inbound_peppol_transport_service.resolve_company_from_participant_id",
            new=AsyncMock(return_value=cid),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/erp/inbound-eracun/peppol/webhook",
                    content=_payload(xml=b"NOT XML AT ALL <<<"),
                    headers={"Content-Type": "application/json"},
                )

        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"


# ── Auth failures ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_invalid_hmac_returns_403(self, app):
        """Wrong HMAC signature → 403."""
        import os
        os.environ["PEPPOL_AP_INBOUND_WEBHOOK_SECRET"] = "real-secret"
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/erp/inbound-eracun/peppol/webhook",
                    content=_payload(xml=b"<Invoice/>"),
                    headers={
                        "Content-Type": "application/json",
                        "X-Peppol-Signature": "deadbeef",
                    },
                )
            assert resp.status_code == 403
        finally:
            os.environ.pop("PEPPOL_AP_INBOUND_WEBHOOK_SECRET", None)

    @pytest.mark.asyncio
    async def test_valid_hmac_accepted(self, app, cid):
        """Correct HMAC signature → request accepted."""
        import hashlib, hmac as _hmac, os
        from services.erp.company_service import CompanyService

        ctx = ERPRequestContext(
            user_id="test", company_id=cid, role="owner",
            grants=["*"], denies=[], request_id=str(uuid4()),
        )
        await CompanyService().upsert({"oib": "47034854402", "name": "Test Buyer"}, ctx)

        xml     = _make_ubl(f"ROUTE-HMAC-{uuid4().hex[:8]}")
        body    = _payload(xml=xml)
        secret  = "test-inbound-secret"
        sig     = _hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        os.environ["PEPPOL_AP_INBOUND_WEBHOOK_SECRET"] = secret
        try:
            with patch(
                "services.erp.inbound_peppol_transport_service.resolve_company_from_participant_id",
                new=AsyncMock(return_value=cid),
            ):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    resp = await client.post(
                        "/api/erp/inbound-eracun/peppol/webhook",
                        content=body,
                        headers={"Content-Type": "application/json", "X-Peppol-Signature": sig},
                    )
            assert resp.status_code == 200
        finally:
            os.environ.pop("PEPPOL_AP_INBOUND_WEBHOOK_SECRET", None)


# ── Payload validation ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_missing_submission_id_returns_400(self, app):
        """Payload without submissionId → 400."""
        import os; os.environ.pop("PEPPOL_AP_INBOUND_WEBHOOK_SECRET", None)
        os.environ.pop("PEPPOL_AP_WEBHOOK_SECRET", None)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/erp/inbound-eracun/peppol/webhook",
                content=json.dumps({"receiverId": "0190:123"}).encode(),
                headers={"Content-Type": "application/json"},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_no_document_bytes_returns_400(self, app, cid):
        """Payload with submissionId but no documentBase64/URL → 400."""
        import os; os.environ.pop("PEPPOL_AP_INBOUND_WEBHOOK_SECRET", None)
        os.environ.pop("PEPPOL_AP_WEBHOOK_SECRET", None)

        with patch(
            "services.erp.inbound_peppol_transport_service.resolve_company_from_participant_id",
            new=AsyncMock(return_value=cid),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/erp/inbound-eracun/peppol/webhook",
                    content=json.dumps({"submissionId": "SID-X", "receiverId": "0190:123"}).encode(),
                    headers={"Content-Type": "application/json"},
                )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_unknown_receiver_returns_404(self, app):
        """Receiver participant_id not registered → 404."""
        import os; os.environ.pop("PEPPOL_AP_INBOUND_WEBHOOK_SECRET", None)
        os.environ.pop("PEPPOL_AP_WEBHOOK_SECRET", None)

        with patch(
            "services.erp.inbound_peppol_transport_service.resolve_company_from_participant_id",
            new=AsyncMock(return_value=None),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/erp/inbound-eracun/peppol/webhook",
                    content=_payload(xml=b"<Invoice/>"),
                    headers={"Content-Type": "application/json"},
                )
        assert resp.status_code == 404


# ── Multi-company routing ─────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_receiver_participant_id_routes_to_correct_company(self, app):
        """Two companies with different participant IDs receive their own invoices."""
        import os
        os.environ.pop("PEPPOL_AP_INBOUND_WEBHOOK_SECRET", None)
        os.environ.pop("PEPPOL_AP_WEBHOOK_SECRET", None)

        from services.erp.company_service import CompanyService

        cid_a = f"company_A_{uuid4().hex}"
        cid_b = f"company_B_{uuid4().hex}"

        for cid, oib in [(cid_a, "47034854402"), (cid_b, "47034854402")]:
            ctx = ERPRequestContext(
                user_id="test", company_id=cid, role="owner",
                grants=["*"], denies=[], request_id=str(uuid4()),
            )
            await CompanyService().upsert({"oib": oib, "name": f"Kupac {cid[-4:]}"}, ctx)

        xml_a = _make_ubl(f"ROUTE-MULTI-A-{uuid4().hex[:8]}")
        xml_b = _make_ubl(f"ROUTE-MULTI-B-{uuid4().hex[:8]}")

        async def _resolve(pid):
            return cid_a if pid == "0190:A" else cid_b

        with patch(
            "services.erp.inbound_peppol_transport_service.resolve_company_from_participant_id",
            new=AsyncMock(side_effect=_resolve),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp_a = await client.post(
                    "/api/erp/inbound-eracun/peppol/webhook",
                    content=_payload(receiver_id="0190:A", xml=xml_a),
                    headers={"Content-Type": "application/json"},
                )
                resp_b = await client.post(
                    "/api/erp/inbound-eracun/peppol/webhook",
                    content=_payload(receiver_id="0190:B", xml=xml_b),
                    headers={"Content-Type": "application/json"},
                )

        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        assert resp_a.json()["status"] == "imported"
        assert resp_b.json()["status"] == "imported"
        # Each invoice belongs to the correct company — vendor_invoice_id is distinct
        assert resp_a.json()["vendor_invoice_id"] != resp_b.json()["vendor_invoice_id"]


# ── Sprint B.1 regression: archive on webhook path ───────────────────────────

class TestPeppolWebhookArchive:

    @pytest.mark.asyncio
    async def test_webhook_import_returns_archive_status_archived(self, app, cid):
        """B.1: webhook with archive=True → response archive_status='archived'."""
        from services.erp.company_service import CompanyService
        import os

        ctx = ERPRequestContext(
            user_id="test", company_id=cid, role="owner",
            grants=["*"], denies=[], request_id=str(uuid4()),
        )
        await CompanyService().upsert({"oib": "47034854402", "name": "Test Buyer"}, ctx)

        xml = _make_ubl(f"ROUTE-ARCH-{uuid4().hex[:8]}")
        os.environ.pop("PEPPOL_AP_INBOUND_WEBHOOK_SECRET", None)
        os.environ.pop("PEPPOL_AP_WEBHOOK_SECRET", None)

        with patch(
            "services.erp.inbound_peppol_transport_service.resolve_company_from_participant_id",
            new=AsyncMock(return_value=cid),
        ), patch(
            "services.erp.inbound_eracun_transport_service._archive_xml_bytes",
            new=AsyncMock(return_value={
                "ok": True,
                "drive_file_id":   "wb-drive-001",
                "drive_folder_id": "wb-folder-001",
                "archived_at":     "2026-04-14T10:00:00+00:00",
            }),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/erp/inbound-eracun/peppol/webhook",
                    content=_payload(xml=xml),
                    headers={"Content-Type": "application/json"},
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"]         == "imported"
        assert body["archive_status"] == "archived", f"Expected archived, got: {body['archive_status']}"

    @pytest.mark.asyncio
    async def test_webhook_archive_failure_import_still_succeeds(self, app, cid):
        """B.1: archive Drive failure → import=imported but archive_status='not_archived'."""
        from services.erp.company_service import CompanyService
        import os

        ctx = ERPRequestContext(
            user_id="test", company_id=cid, role="owner",
            grants=["*"], denies=[], request_id=str(uuid4()),
        )
        await CompanyService().upsert({"oib": "47034854402", "name": "Test Buyer"}, ctx)

        xml = _make_ubl(f"ROUTE-ARCHFAIL-{uuid4().hex[:8]}")
        os.environ.pop("PEPPOL_AP_INBOUND_WEBHOOK_SECRET", None)
        os.environ.pop("PEPPOL_AP_WEBHOOK_SECRET", None)

        with patch(
            "services.erp.inbound_peppol_transport_service.resolve_company_from_participant_id",
            new=AsyncMock(return_value=cid),
        ), patch(
            "services.erp.inbound_eracun_transport_service._archive_xml_bytes",
            new=AsyncMock(return_value={"ok": False, "error": "Drive quota exceeded"}),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/erp/inbound-eracun/peppol/webhook",
                    content=_payload(xml=xml),
                    headers={"Content-Type": "application/json"},
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"]         == "imported",      f"Import should succeed: {body}"
        assert body["archive_status"] == "not_archived",  f"Archive failed but: {body['archive_status']}"
