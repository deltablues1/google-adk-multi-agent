"""
Sprint C2.0 + C2.1 regression tests
=====================================
C2.0 — Peppol identity fields in company_settings
C2.1 — Real AP adapter in outbound_dispatch_service (stub fallback + mocked AP)

What is locked here:
  - peppol_participant_id and peppol_scheme stored and returned by CompanyService
  - dispatch_invoice("peppol", ...) returns stub when PEPPOL_AP_ENDPOINT unset
  - dispatch_invoice("peppol", ...) calls AP and returns submission_id when configured
  - AP HTTP 4xx → ok=False with error
  - Missing participant_id or ubl_xml → ok=False (guard, no AP call)
  - Sender ID derived from company_settings when PEPPOL_AP_SENDER_ID not set
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from services.erp.request_context import ERPRequestContext

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


def make_ctx(company_id: str, role: str = "owner") -> ERPRequestContext:
    return ERPRequestContext(
        user_id="test-c2",
        company_id=company_id,
        role=role,
        grants=set(),
        denies=set(),
        request_id=str(uuid4()),
    )


@pytest.fixture
def cid():
    return f"test_c2_{uuid4().hex}"


def _invoice_doc(company_id: str = "co1", ubl_xml: str = "<Invoice/>") -> dict:
    return {
        "invoice_id":   "B2B-001",
        "display_id":   "B2B-001",
        "company_id":   company_id,
        "seller_name":  "Prodavatelj d.o.o.",
        "customer_name": "Kupac d.o.o.",
        "issue_date":   "2026-04-10",
        "total_gross":  125.0,
        "currency":     "EUR",
        "ubl_xml":      ubl_xml,
    }


# ── C2.0: Peppol fields in company_settings ───────────────────────────────────

class TestPeppolCompanySettings:

    @pytest.mark.asyncio
    async def test_upsert_stores_peppol_participant_id(self, cid):
        """peppol_participant_id is persisted and returned by upsert."""
        from services.erp.company_service import CompanyService

        # Use cid-derived Peppol ID so parallel/repeated runs don't collide in Firestore
        peppol_id = f"0190:{cid[-11:]}"
        ctx = make_ctx(cid)
        result = await CompanyService().upsert({
            "oib":                   "47034854402",
            "name":                  "Peppol Firma d.o.o.",
            "peppol_participant_id": peppol_id,
            "peppol_scheme":         "0190",
        }, ctx)

        assert result["peppol_participant_id"] == peppol_id
        assert result["peppol_scheme"] == "0190"

    @pytest.mark.asyncio
    async def test_upsert_default_peppol_scheme(self, cid):
        """When peppol_scheme not provided, defaults to '0190'."""
        from services.erp.company_service import CompanyService

        ctx = make_ctx(cid)
        result = await CompanyService().upsert({
            "oib":  "47034854402",
            "name": "No Scheme Firma d.o.o.",
        }, ctx)

        assert result["peppol_scheme"] == "0190", (
            "Default peppol_scheme must be '0190' (Croatian OIB scheme)"
        )

    @pytest.mark.asyncio
    async def test_get_company_settings_includes_peppol(self, cid):
        """get_company_settings() returns peppol fields."""
        from services.erp.company_service import CompanyService, get_company_settings

        peppol_id = f"0190:{cid[-11:]}"
        ctx = make_ctx(cid)
        await CompanyService().upsert({
            "oib":                   "47034854402",
            "name":                  "Test Firma",
            "peppol_participant_id": peppol_id,
        }, ctx)

        cs = await get_company_settings(cid)
        assert cs.get("peppol_participant_id") == peppol_id
        assert cs.get("peppol_scheme") == "0190"

    @pytest.mark.asyncio
    async def test_patch_peppol_participant_id(self, cid):
        """PATCH updates peppol_participant_id without overwriting other fields."""
        from services.erp.company_service import CompanyService

        peppol_id = f"0190:{cid[-11:]}"
        ctx = make_ctx(cid)
        await CompanyService().upsert({
            "oib":  "47034854402",
            "name": "Patch Firma d.o.o.",
        }, ctx)

        patched = await CompanyService().patch({
            "peppol_participant_id": peppol_id,
            "peppol_scheme":         "0190",
        }, ctx)

        assert patched["peppol_participant_id"] == peppol_id
        assert patched["name"] == "Patch Firma d.o.o.", "Unrelated fields must survive patch"


# ── C2.1: Peppol dispatch — stub mode ─────────────────────────────────────────

class TestPeppolDispatchStub:
    """When PEPPOL_AP_ENDPOINT is not set, dispatch_invoice must return a stub."""

    @pytest.mark.asyncio
    async def test_stub_mode_when_endpoint_not_set(self):
        from services.erp.outbound_dispatch_service import dispatch_invoice

        with patch.dict("os.environ", {}, clear=False):
            # Ensure endpoint not in env
            import os
            os.environ.pop("PEPPOL_AP_ENDPOINT", None)

            result = await dispatch_invoice(
                _invoice_doc(), "peppol", "0190:22222222220"
            )

        assert result["ok"] is True
        assert result["_stub"] is True
        assert result["external_submission_id"].startswith("PEPPOL-STUB-")
        assert result["method"] == "peppol"

    @pytest.mark.asyncio
    async def test_missing_participant_id_returns_error(self):
        from services.erp.outbound_dispatch_service import dispatch_invoice

        result = await dispatch_invoice(_invoice_doc(), "peppol", "")

        assert result["ok"] is False
        assert "participant" in result["error"].lower() or "delivery_target" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_missing_ubl_xml_returns_error(self):
        from services.erp.outbound_dispatch_service import dispatch_invoice

        doc = _invoice_doc(ubl_xml="")
        result = await dispatch_invoice(doc, "peppol", "0190:22222222220")

        assert result["ok"] is False
        assert "UBL" in result["error"]


# ── C2.1: Peppol dispatch — real AP (mocked) ──────────────────────────────────

class TestPeppolDispatchRealAP:
    """When PEPPOL_AP_ENDPOINT is set, dispatch_invoice must call the AP."""

    def _make_mock_response(self, status_code: int = 202, json_body: dict = None, text: str = ""):
        resp = MagicMock()
        resp.status_code = status_code
        resp.text = text
        if json_body is not None:
            resp.json = MagicMock(return_value=json_body)
        else:
            resp.json = MagicMock(side_effect=ValueError("no json"))
        resp.headers = {}
        return resp

    @pytest.mark.asyncio
    async def test_real_ap_202_with_submission_id(self):
        from services.erp.outbound_dispatch_service import dispatch_invoice

        mock_resp = self._make_mock_response(
            status_code=202,
            json_body={"submission_id": "AP-REAL-12345"},
        )

        with patch.dict("os.environ", {
            "PEPPOL_AP_ENDPOINT": "https://ap.example.com/send",
            "PEPPOL_AP_API_KEY":  "test-key",
            "PEPPOL_AP_SENDER_ID": "0190:11111111110",
        }):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = AsyncMock(return_value=mock_resp)
                mock_client_cls.return_value = mock_client

                result = await dispatch_invoice(
                    _invoice_doc(), "peppol", "0190:22222222220"
                )

        assert result["ok"] is True
        assert result["external_submission_id"] == "AP-REAL-12345"
        assert result["method"] == "peppol"
        assert "_stub" not in result

    @pytest.mark.asyncio
    async def test_real_ap_submissionId_camelcase(self):
        """AP returning submissionId (camelCase) is handled."""
        from services.erp.outbound_dispatch_service import dispatch_invoice

        mock_resp = self._make_mock_response(
            status_code=200,
            json_body={"submissionId": "FINA-9876"},
        )

        with patch.dict("os.environ", {
            "PEPPOL_AP_ENDPOINT": "https://ap.fina.hr/send",
            "PEPPOL_AP_API_KEY":  "key",
            "PEPPOL_AP_SENDER_ID": "0190:11111111110",
        }):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = AsyncMock(return_value=mock_resp)
                mock_client_cls.return_value = mock_client

                result = await dispatch_invoice(
                    _invoice_doc(), "peppol", "0190:33333333330"
                )

        assert result["ok"] is True
        assert result["external_submission_id"] == "FINA-9876"

    @pytest.mark.asyncio
    async def test_real_ap_location_header_fallback(self):
        """When body has no id fields, Location header is used for submission_id."""
        from services.erp.outbound_dispatch_service import dispatch_invoice

        mock_resp = self._make_mock_response(status_code=201)
        mock_resp.headers = {"Location": "https://ap.example.com/submissions/LOC-001"}

        with patch.dict("os.environ", {
            "PEPPOL_AP_ENDPOINT":  "https://ap.example.com/send",
            "PEPPOL_AP_SENDER_ID": "0190:11111111110",
        }):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = AsyncMock(return_value=mock_resp)
                mock_client_cls.return_value = mock_client

                result = await dispatch_invoice(
                    _invoice_doc(), "peppol", "0190:44444444440"
                )

        assert result["ok"] is True
        assert result["external_submission_id"] == "LOC-001"

    @pytest.mark.asyncio
    async def test_real_ap_4xx_returns_error(self):
        """AP returning HTTP 400 → ok=False with error message."""
        from services.erp.outbound_dispatch_service import dispatch_invoice

        mock_resp = self._make_mock_response(
            status_code=400, text="Invalid recipient Peppol ID"
        )

        with patch.dict("os.environ", {
            "PEPPOL_AP_ENDPOINT":  "https://ap.example.com/send",
            "PEPPOL_AP_SENDER_ID": "0190:11111111110",
        }):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = AsyncMock(return_value=mock_resp)
                mock_client_cls.return_value = mock_client

                result = await dispatch_invoice(
                    _invoice_doc(), "peppol", "0190:55555555550"
                )

        assert result["ok"] is False
        assert "400" in result["error"]

    @pytest.mark.asyncio
    async def test_real_ap_exception_returns_error(self):
        """Network exception → ok=False (no crash)."""
        from services.erp.outbound_dispatch_service import dispatch_invoice

        with patch.dict("os.environ", {
            "PEPPOL_AP_ENDPOINT":  "https://ap.example.com/send",
            "PEPPOL_AP_SENDER_ID": "0190:11111111110",
        }):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = AsyncMock(side_effect=ConnectionError("timeout"))
                mock_client_cls.return_value = mock_client

                result = await dispatch_invoice(
                    _invoice_doc(), "peppol", "0190:66666666660"
                )

        assert result["ok"] is False
        assert result["method"] == "peppol"

    @pytest.mark.asyncio
    async def test_sender_id_derived_from_company_settings(self, cid):
        """When PEPPOL_AP_SENDER_ID not set, sender is derived from company_settings."""
        from services.erp.company_service import CompanyService
        from services.erp.outbound_dispatch_service import dispatch_invoice

        peppol_id = f"0190:{cid[-11:]}"
        ctx = make_ctx(cid)
        await CompanyService().upsert({
            "oib":                   "47034854402",
            "name":                  "Peppol Sender d.o.o.",
            "peppol_participant_id": peppol_id,
            "peppol_scheme":         "0190",
        }, ctx)

        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.json = MagicMock(return_value={"submission_id": "AP-FROM-CS-001"})
        mock_resp.headers = {}

        captured_params = {}

        async def _mock_post(url, **kwargs):
            captured_params.update(kwargs.get("params", {}))
            return mock_resp

        with patch.dict("os.environ", {
            "PEPPOL_AP_ENDPOINT": "https://ap.example.com/send",
            "PEPPOL_AP_API_KEY":  "key",
        }):
            import os
            os.environ.pop("PEPPOL_AP_SENDER_ID", None)

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = AsyncMock(side_effect=_mock_post)
                mock_client_cls.return_value = mock_client

                result = await dispatch_invoice(
                    _invoice_doc(company_id=cid), "peppol", "0190:77777777770"
                )

        assert result["ok"] is True
        assert captured_params.get("sender") == peppol_id, (
            "Sender ID must be derived from company_settings.peppol_participant_id"
        )

    @pytest.mark.asyncio
    async def test_sender_id_derived_from_oib_when_no_peppol_id(self, cid):
        """When peppol_participant_id is empty, fallback to scheme:oib from company_settings."""
        from services.erp.company_service import CompanyService
        from services.erp.outbound_dispatch_service import dispatch_invoice

        ctx = make_ctx(cid)
        await CompanyService().upsert({
            "oib":          "47034854402",
            "name":         "OIB Fallback d.o.o.",
            "peppol_scheme": "0190",
            # no peppol_participant_id
        }, ctx)

        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.json = MagicMock(return_value={"submission_id": "AP-OIB-FALLBACK"})
        mock_resp.headers = {}
        captured_params = {}

        async def _mock_post(url, **kwargs):
            captured_params.update(kwargs.get("params", {}))
            return mock_resp

        with patch.dict("os.environ", {"PEPPOL_AP_ENDPOINT": "https://ap.example.com/send"}):
            import os
            os.environ.pop("PEPPOL_AP_SENDER_ID", None)

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = AsyncMock(side_effect=_mock_post)
                mock_client_cls.return_value = mock_client

                result = await dispatch_invoice(
                    _invoice_doc(company_id=cid), "peppol", "0190:88888888880"
                )

        assert result["ok"] is True
        assert captured_params.get("sender") == "0190:47034854402", (
            "When peppol_participant_id is empty, sender must be scheme:oib"
        )
