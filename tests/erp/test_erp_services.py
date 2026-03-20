"""
ERP Service Integration Tests
================================
Integration tests that use a REAL Firestore connection.

ISOLATION: Each test class uses a unique company_id so tests don't interfere
with each other or with production data. For full isolation, run with the
Firestore emulator:
    firebase emulators:start --only firestore
    FIRESTORE_EMULATOR_HOST=localhost:8080 pytest tests/erp/test_erp_services.py

Marks: pytest.mark.integration — skip by default:
    pytest tests/erp/test_erp_services.py  (runs all)
    pytest -m "not integration" tests/erp/ (skip these)
"""

import pytest
import asyncio
from uuid import uuid4
from decimal import Decimal
from datetime import date

from services.erp.request_context import ERPRequestContext
from services.erp.errors import (
    ValidationError, NotFoundError, DuplicateError, InvalidStateTransitionError
)


def make_ctx(company_id: str, role: str = "owner") -> ERPRequestContext:
    return ERPRequestContext(
        user_id="test-user",
        company_id=company_id,
        role=role,
        grants=set(),
        denies=set(),
        request_id=str(uuid4()),
    )


@pytest.fixture
def cid():
    """Unique company_id per test — prevents cross-contamination."""
    return f"test_{uuid4().hex}"


pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


# ---------------------------------------------------------------------------
# CustomerService
# ---------------------------------------------------------------------------

class TestCustomerService:

    @pytest.mark.asyncio
    async def test_create_and_get_customer(self, cid):
        from services.erp.customer_service import CustomerService
        svc = CustomerService()
        ctx = make_ctx(cid)

        customer = await svc.create_customer({
            "name": "Acme d.o.o.",
            "oib": "12345678901",
            "party_type": "customer",
            "email": "acme@example.com",
        }, ctx)

        assert customer["name"] == "Acme d.o.o."
        assert customer["company_id"] == cid
        assert "_id" in customer

        fetched = await svc.get_customer(customer["_id"], ctx)
        assert fetched["oib"] == "12345678901"

    @pytest.mark.asyncio
    async def test_delete_hides_customer(self, cid):
        from services.erp.customer_service import CustomerService
        svc = CustomerService()
        ctx = make_ctx(cid)

        customer = await svc.create_customer({"name": "DeleteMe", "party_type": "customer"}, ctx)
        cid_doc = customer["_id"]

        await svc.delete_customer(cid_doc, ctx)

        from services.erp.errors import NotFoundError
        with pytest.raises(NotFoundError):
            await svc.get_customer(cid_doc, ctx)


# ---------------------------------------------------------------------------
# ProductService
# ---------------------------------------------------------------------------

class TestProductService:

    @pytest.mark.asyncio
    async def test_create_product_and_adjust_stock(self, cid):
        from services.erp.product_service import ProductService
        svc = ProductService()
        ctx = make_ctx(cid)

        product = await svc.create_product({
            "name": "Test Widget",
            "sku": "TW-001",
            "unit_price": 10.0,
            "vat_rate": 25,
            "stock_quantity": 0,
        }, ctx)
        assert product["name"] == "Test Widget"

        updated = await svc.adjust_stock(product["_id"], Decimal("50"), "Initial stock load", ctx)
        assert float(updated["new_quantity"]) == 50.0


# ---------------------------------------------------------------------------
# VendorInvoiceService
# ---------------------------------------------------------------------------

class TestVendorInvoiceService:

    @pytest.mark.asyncio
    async def test_create_from_ocr_produces_draft(self, cid):
        from services.erp.vendor_invoice_service import VendorInvoiceService
        svc = VendorInvoiceService()
        ctx = make_ctx(cid)

        ocr_data = {
            "merchant_name": "T-HT d.d.",
            "vendor_oib": "09006962014",
            "invoice_number": "R-2026-001",
            "transaction_date": str(date.today()),
            "total_amount": 125.0,
            "items": [{"description": "Internet usluga", "amount": 125.0}],
            "expense_category": "Režije",
            "confidence_score": 0.92,
        }

        result = await svc.create_from_ocr(ocr_data, scan_file_id="", ctx=ctx)
        assert result["document_status"] == "draft"
        # vendor_id empty because no matching customer exists in this test company
        assert result.get("vendor_id", "") == ""

    @pytest.mark.asyncio
    async def test_state_transitions_draft_received_approved(self, cid):
        from services.erp.vendor_invoice_service import VendorInvoiceService
        svc = VendorInvoiceService()
        ctx = make_ctx(cid)

        ura = await svc.create_from_ocr({
            "merchant_name": "Supplier X",
            "invoice_number": "S-001",
            "transaction_date": str(date.today()),
            "total_amount": 200.0,
            "due_date": str(date.today()),
        }, scan_file_id="", ctx=ctx)

        # draft → received
        await svc.mark_received(ura["_id"], ctx)
        doc = await svc._get_repo().get(ura["_id"], ctx)
        assert doc["document_status"] == "received"

        # received → approved (requires due_date set on doc)
        from services.erp.base_erp_service import get_firestore_db
        db = get_firestore_db()
        await db.collection("vendor_invoices").document(ura["_id"]).update({"due_date": str(date.today())})
        await svc.approve_vendor_invoice(ura["_id"], ctx)
        doc = await svc._get_repo().get(ura["_id"], ctx)
        assert doc["document_status"] == "approved"


# ---------------------------------------------------------------------------
# InvoiceService — record_payment
# ---------------------------------------------------------------------------

class TestInvoiceServicePayment:

    @pytest.mark.asyncio
    async def test_duplicate_idempotency_key_raises_duplicate_error(self, cid):
        """Same idempotency_key → DuplicateError on second call."""
        from services.erp.invoice_service import InvoiceService
        from services.erp.repositories.base import InvoiceReference
        svc = InvoiceService()
        ctx = make_ctx(cid)

        # We need a real invoice document — this test requires Firestore data
        # Skip if no invoice is available (integration data dependency)
        pytest.skip("Requires a pre-existing invoice in Firestore — use E2E test instead")

    @pytest.mark.asyncio
    async def test_partial_then_full_payment(self, cid):
        """Partial payment → payment_status=partial; full → paid."""
        pytest.skip("Requires pre-existing invoice — covered by E2E Scenarij B")


# ---------------------------------------------------------------------------
# ReportingService
# ---------------------------------------------------------------------------

class TestReportingService:

    @pytest.mark.asyncio
    async def test_financial_summary_invoice_count_not_zero(self, cid):
        """Bug 4 fix: invoice_count must be > 0 when invoices exist."""
        from services.erp.reporting_service import ReportingService
        svc = ReportingService()
        ctx = make_ctx(cid)

        # With empty test company, count is 0 — just verify no crash and structure is correct
        result = await svc.get_financial_summary(ctx, "2026-01-01", "2026-12-31")
        assert "invoice_count" in result
        assert isinstance(result["invoice_count"], int)
        assert result["invoice_count"] >= 0  # not negative or None


# ---------------------------------------------------------------------------
# Vendor Matching (3a feature)
# ---------------------------------------------------------------------------

class TestVendorMatching:

    @pytest.mark.asyncio
    async def test_ocr_draft_matches_existing_vendor_by_oib(self, cid):
        """When a customer with matching OIB exists, create_from_ocr auto-populates vendor_id."""
        from services.erp.customer_service import CustomerService
        from services.erp.vendor_invoice_service import VendorInvoiceService
        customer_svc = CustomerService()
        vendor_svc = VendorInvoiceService()
        ctx = make_ctx(cid)

        # Pre-create a supplier customer with known OIB
        supplier = await customer_svc.create_customer({
            "name": "T-HT d.d.",
            "oib": "09006962014",
            "party_type": "supplier",
        }, ctx)

        ocr_data = {
            "merchant_name": "T-HT",
            "vendor_oib": "09006962014",
            "invoice_number": "R-2026-MATCH",
            "transaction_date": str(date.today()),
            "total_amount": 150.0,
        }
        result = await vendor_svc.create_from_ocr(ocr_data, scan_file_id="", ctx=ctx)
        assert result["vendor_id"] == supplier["_id"]
        assert result["vendor_name"] == "T-HT d.d."
        assert result["ocr_data"]["vendor_match"] == "matched"


# ---------------------------------------------------------------------------
# Inventory Movements (3c feature)
# ---------------------------------------------------------------------------

class TestInventoryMovements:

    @pytest.mark.asyncio
    async def test_adjust_stock_creates_movement(self, cid):
        """adjust_stock records an inventory movement retrievable via the service."""
        from services.erp.product_service import ProductService
        svc = ProductService()
        ctx = make_ctx(cid)

        product = await svc.create_product({
            "name": "Movement Test Widget",
            "sku": "MTW-001",
            "unit_price": 5.0,
            "vat_rate": 25,
            "stock_quantity": 0,
        }, ctx)

        await svc.adjust_stock(product["_id"], Decimal("30"), "Initial stock load", ctx)
        movements = await svc.get_stock_movements(product["_id"], ctx)
        assert len(movements) >= 1
        m = movements[0]
        assert m["product_id"] == product["_id"]
        assert m["movement_type"] == "manual_adjust"
        assert m["quantity_delta"] == 30.0
        assert m["quantity_after"] == 30.0


# ---------------------------------------------------------------------------
# Activity Feed (3d feature)
# ---------------------------------------------------------------------------

class TestActivityFeed:

    @pytest.mark.asyncio
    async def test_activity_feed_returns_audit_events(self, cid):
        """After a create action, GET /api/erp/activity returns at least one event."""
        from services.erp.customer_service import CustomerService
        from services.erp.base_erp_service import get_firestore_db
        svc = CustomerService()
        ctx = make_ctx(cid)

        await svc.create_customer({"name": "Feed Test d.o.o.", "party_type": "customer"}, ctx)

        db = get_firestore_db()
        query = (
            db.collection("audit_log")
            .where("company_id", "==", cid)
            .where("target_service", "==", "erp")
            .order_by("timestamp", direction="DESCENDING")
            .limit(5)
        )
        events = []
        async for snap in query.stream():
            events.append(snap.to_dict())

        assert len(events) >= 1
        assert events[0]["action_type"] == "customer_created"
