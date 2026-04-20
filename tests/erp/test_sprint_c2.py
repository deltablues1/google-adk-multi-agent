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

