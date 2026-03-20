"""
ERP End-to-End Tests
====================
Full workflow E2E tests that use Firestore.

ISOLATION: Unique company_id per test run.
Run with Firestore emulator for fastest, safest execution:
    firebase emulators:start --only firestore
    FIRESTORE_EMULATOR_HOST=localhost:8080 pytest tests/erp/test_erp_e2e.py

Scenario A: OCR → URA draft → mark_received → approve → vendor payment record
Scenario B: Customer invoice → partial payment → full payment → aging = 0
"""

import pytest
from uuid import uuid4
from decimal import Decimal
from datetime import date, timedelta

from services.erp.request_context import ERPRequestContext


def make_ctx(company_id: str) -> ERPRequestContext:
    return ERPRequestContext(
        user_id="e2e-test-user",
        company_id=company_id,
        role="owner",
        grants=set(),
        denies=set(),
        request_id=str(uuid4()),
    )


@pytest.fixture
def cid():
    return f"test_{uuid4().hex}"


pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


class TestScenarioA_URAWorkflow:
    """
    Scenarij A: OCR scan → URA draft → Potvrdi primitak → Odobri → Uplata
    """

    @pytest.mark.asyncio
    async def test_full_ura_workflow(self, cid):
        from services.erp.vendor_invoice_service import VendorInvoiceService
        svc = VendorInvoiceService()
        ctx = make_ctx(cid)

        # Step 1: OCR data arrives (simulated — no real image)
        ocr_data = {
            "merchant_name": "HEP d.d.",
            "vendor_oib": "28921978587",
            "invoice_number": "HEP-2026-001",
            "transaction_date": str(date.today()),
            "total_amount": 250.0,
            "items": [{"description": "Električna energija", "amount": 250.0}],
            "expense_category": "Režije",
            "confidence_score": 0.95,
            "due_date": str(date.today()),
        }

        ura = await svc.create_from_ocr(ocr_data, scan_file_id="", ctx=ctx)
        assert ura["document_status"] == "draft"
        ura_id = ura["_id"]

        # Step 2: mark_received
        await svc.mark_received(ura_id, ctx)
        doc = await svc._get_repo().get(ura_id, ctx)
        assert doc["document_status"] == "received"

        # Step 3: approve
        await svc.approve_vendor_invoice(ura_id, ctx)
        doc = await svc._get_repo().get(ura_id, ctx)
        assert doc["document_status"] == "approved"

        # Step 4: record vendor payment
        payment = await svc.record_payment(
            vendor_invoice_id=ura_id,
            amount=Decimal("250.0"),
            payment_date=str(date.today()),
            payment_method="transfer",
            reference="",
            ctx=ctx,
        )
        assert payment is not None

        # Final state
        doc = await svc._get_repo().get(ura_id, ctx)
        assert doc.get("payment_status") == "paid"


class TestScenarioB_CustomerInvoicePayments:
    """
    Scenarij B: Customer invoice → partial → full payment
    Requires a real customer invoice to exist in Firestore.
    """

    @pytest.mark.asyncio
    async def test_partial_then_full_payment_flow(self, cid):
        """
        This scenario requires an actual fiscalized/issued customer invoice.
        Until we have a test invoice factory, this test serves as placeholder.
        The Bug 2 fix ensures party_id and party_name are populated.
        The Bug 4 fix ensures invoice_count > 0 in financial summary.
        """
        pytest.skip(
            "Scenarij B requires a pre-existing outgoing invoice. "
            "Use manual testing or implement invoice factory fixture."
        )
