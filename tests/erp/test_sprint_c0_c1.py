"""
Sprint C0 + C1 + C0.1 + C1.1 regression tests
===============================================
C0:   company_settings store, write-side date normalization, query correctness
C1:   ERP-fiscalization bridge write-back
C0.1: IBAN validation, accountant role company:read/write + invoice:fiscalize
C1.1: fiscalize_b2c_invoice() service, /invoices/b2c/{id}/fiscalize route,
      fiscalization-status route
"""

import pytest
from uuid import uuid4
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from services.erp.request_context import ERPRequestContext
from services.erp.errors import NotFoundError, ValidationError

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


def make_ctx(company_id: str, role: str = "owner") -> ERPRequestContext:
    return ERPRequestContext(
        user_id="test-user-c0",
        company_id=company_id,
        role=role,
        grants=set(),
        denies=set(),
        request_id=str(uuid4()),
    )


@pytest.fixture
def cid():
    return f"test_c0_{uuid4().hex}"


# ── C0: Company Settings ──────────────────────────────────────────────────────

class TestCompanySettings:

    @pytest.mark.asyncio
    async def test_upsert_and_get(self, cid):
        from services.erp.company_service import get_company_service
        svc = get_company_service()
        ctx = make_ctx(cid)

        stored = await svc.upsert({
            "oib": "47034854402",
            "name": "LUX TECH D.O.O.",
            "iban": "HR1210010051863000160",
            "vat_registered": True,
        }, ctx)
        assert stored["oib"] == "47034854402"
        assert stored["name"] == "LUX TECH D.O.O."

        fetched = await svc.get(ctx)
        assert fetched["oib"] == "47034854402"

    @pytest.mark.asyncio
    async def test_get_company_oib_helper(self, cid):
        from services.erp.company_service import get_company_service, get_company_oib
        await get_company_service().upsert({"oib": "12345678901", "name": "Test d.o.o."}, make_ctx(cid))
        oib = await get_company_oib(cid)
        assert oib == "12345678901"

    @pytest.mark.asyncio
    async def test_get_company_oib_returns_empty_when_not_configured(self, cid):
        from services.erp.company_service import get_company_oib
        oib = await get_company_oib(f"nonexistent_{uuid4().hex}")
        assert oib == ""

    @pytest.mark.asyncio
    async def test_invalid_oib_raises_validation_error(self, cid):
        from services.erp.company_service import get_company_service
        with pytest.raises(ValidationError) as exc_info:
            await get_company_service().upsert({"oib": "1234"}, make_ctx(cid))
        assert exc_info.value.code == "INVALID_OIB"

    @pytest.mark.asyncio
    async def test_patch_updates_single_field(self, cid):
        from services.erp.company_service import get_company_service
        svc = get_company_service()
        ctx = make_ctx(cid)
        await svc.upsert({"oib": "47034854402", "name": "Original"}, ctx)
        updated = await svc.patch({"name": "Updated Name"}, ctx)
        assert updated["name"] == "Updated Name"
        assert updated["oib"] == "47034854402"

    @pytest.mark.asyncio
    async def test_get_raises_not_found_when_not_configured(self):
        from services.erp.company_service import get_company_service
        ctx = make_ctx(f"nocompany_{uuid4().hex}")
        with pytest.raises(NotFoundError):
            await get_company_service().get(ctx)


# ── C0: Write-side date normalization ────────────────────────────────────────

class TestWriteSideDateNormalization:

    @pytest.mark.asyncio
    async def test_outbound_b2b_writes_date_field(self, cid):
        from services.erp.outbound_b2b_service import OutboundB2BService
        svc = OutboundB2BService()
        ctx = make_ctx(cid)
        today = str(date.today())

        inv = await svc.create({
            "customer_name": "Date Test d.o.o.", "customer_oib": "11111111110",
            "seller_name": "Prodavac", "seller_oib": "98765432100",
            "seller_iban": "HR1210010051863000160",
            "issue_date": today, "due_date": today,
            "items": [{"name": "X", "description": "X", "quantity": 1,
                       "unit": "kom", "unit_price": 100.0, "vat_rate": 25}],
        }, ctx)

        assert inv.get("date") == today, "date must equal issue_date"
        assert inv.get("issue_date") == today

    @pytest.mark.asyncio
    async def test_b2c_convert_writes_date_field(self, cid):
        from services.erp.quote_service import QuoteService
        from services.erp.customer_service import CustomerService
        from services.erp.base_erp_service import get_firestore_db

        svc = QuoteService()
        ctx = make_ctx(cid)
        today = str(date.today())

        cust = await CustomerService().create_customer(
            {"name": "Test Kupac", "oib": "22222222220", "party_type": "customer"}, ctx
        )
        q = await svc.create_quote({
            "customer_id": cust["_id"],
            "customer_name": "Test Kupac", "customer_oib": "22222222220",
            "valid_until": str(date.today()),
            "items": [{"name": "A", "quantity": 1, "unit_price": 50.0, "vat_rate": 25}],
        }, ctx)
        await svc.mark_sent(q["quote_id"], ctx)
        await svc.accept_quote(q["quote_id"], ctx)

        result = await svc.convert_to_invoice(q["quote_id"], "b2c", ctx)
        snap = await get_firestore_db().collection("invoices_b2c").document(result["invoice_id"]).get()
        doc = snap.to_dict() or {}
        assert doc.get("date") == today, "date field must be written by convert_to_invoice"


# ── C0: Company Settings API ─────────────────────────────────────────────────

class TestCompanySettingsAPI:

    @pytest.fixture(scope="class")
    def company_id(self):
        return f"test_api_c0_{uuid4().hex}"

    @pytest.fixture(scope="class")
    def app(self, company_id):
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse
        from services.erp.errors import BusinessError
        from web.erp_routes import router as erp_router, get_erp_ctx

        app = FastAPI()

        @app.exception_handler(BusinessError)
        async def biz_err(request: Request, exc: BusinessError):
            return JSONResponse(
                status_code=exc.http_status,
                content={"code": exc.code, "message": exc.message, "field": exc.field},
            )

        app.include_router(erp_router)

        def _ctx():
            return ERPRequestContext(
                user_id="test-user-api", company_id=company_id,
                role="owner", grants=["*"], denies=[], request_id=str(uuid4()),
            )

        app.dependency_overrides[get_erp_ctx] = _ctx
        return app

    @pytest.mark.asyncio
    async def test_put_and_get_company_settings(self, app):
        from httpx import AsyncClient, ASGITransport
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.put("/api/erp/company/settings", json={
                "oib": "47034854402", "name": "API Test d.o.o."
            })
            assert r.status_code == 200
            assert r.json()["oib"] == "47034854402"

            r2 = await client.get("/api/erp/company/settings")
            assert r2.status_code == 200
            assert r2.json()["name"] == "API Test d.o.o."

    @pytest.mark.asyncio
    async def test_patch_company_settings(self, app):
        from httpx import AsyncClient, ASGITransport
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.put("/api/erp/company/settings", json={"oib": "47034854402", "name": "Old"})
            r = await client.patch("/api/erp/company/settings", json={"name": "New Name"})
            assert r.status_code == 200
            assert r.json()["name"] == "New Name"
            assert r.json()["oib"] == "47034854402"

    @pytest.mark.asyncio
    async def test_get_unconfigured_returns_404(self, app):
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse
        from services.erp.errors import BusinessError
        from web.erp_routes import router as erp_router, get_erp_ctx

        empty_app = FastAPI()

        @empty_app.exception_handler(BusinessError)
        async def biz_err(request: Request, exc: BusinessError):
            return JSONResponse(status_code=exc.http_status, content={"code": exc.code})

        empty_app.include_router(erp_router)

        def _ctx():
            return ERPRequestContext(
                user_id="x", company_id=f"nocompany_{uuid4().hex}",
                role="owner", grants=["*"], denies=[], request_id=str(uuid4()),
            )

        empty_app.dependency_overrides[get_erp_ctx] = _ctx

        from httpx import AsyncClient, ASGITransport
        async with AsyncClient(transport=ASGITransport(app=empty_app), base_url="http://test") as client:
            r = await client.get("/api/erp/company/settings")
        assert r.status_code == 404

# ── C0.1: IBAN validation ─────────────────────────────────────────────────────

@pytest.mark.unit
class TestIBANValidationAsync:
    """Async IBAN tests (Firestore required). Sync logic tests are in test_unit_sync.py."""

    @pytest.mark.asyncio
    async def test_upsert_rejects_invalid_iban(self, cid):
        from services.erp.company_service import get_company_service
        from services.erp.errors import ValidationError
        with pytest.raises(ValidationError) as exc_info:
            await get_company_service().upsert(
                {"oib": "47034854402", "iban": "HR00000"}, make_ctx(cid)
            )
        assert exc_info.value.code == "INVALID_IBAN"

    @pytest.mark.asyncio
    async def test_upsert_accepts_valid_iban(self, cid):
        from services.erp.company_service import get_company_service
        doc = await get_company_service().upsert(
            {"oib": "47034854402", "iban": "HR1210010051863000160"}, make_ctx(cid)
        )
        assert doc["iban"] == "HR1210010051863000160"

    @pytest.mark.asyncio
    async def test_patch_rejects_invalid_iban(self, cid):
        from services.erp.company_service import get_company_service
        from services.erp.errors import ValidationError
        svc = get_company_service()
        ctx = make_ctx(cid)
        await svc.upsert({"oib": "47034854402"}, ctx)
        with pytest.raises(ValidationError) as exc_info:
            await svc.patch({"iban": "NOTANIBAN"}, ctx)
        assert exc_info.value.code == "INVALID_IBAN"


# ── C0.1: Role permissions ────────────────────────────────────────────────────

@pytest.mark.unit
class TestRolePermissionsAsync:
    """Async role tests (Firestore required). Sync table checks are in test_unit_sync.py."""

    @pytest.mark.asyncio
    async def test_accountant_can_get_company_settings(self, cid):
        from services.erp.company_service import get_company_service
        ctx_owner = make_ctx(cid, "owner")
        ctx_acc   = make_ctx(cid, "accountant")
        await get_company_service().upsert({"oib": "47034854402", "name": "Acc Test"}, ctx_owner)
        doc = await get_company_service().get(ctx_acc)
        assert doc["oib"] == "47034854402"

    @pytest.mark.asyncio
    async def test_viewer_cannot_write_company_settings(self, cid):
        from services.erp.company_service import get_company_service
        from services.erp.errors import InsufficientPermissionError
        ctx_viewer = make_ctx(cid, "viewer")
        with pytest.raises(InsufficientPermissionError):
            await get_company_service().upsert({"oib": "47034854402"}, ctx_viewer)

# ── C1: Fiscalization bridge unit tests ──────────────────────────────────────

@pytest.mark.unit
class TestFiscalizationBridge:

    @pytest.mark.asyncio
    async def test_write_back_b2c_success(self):
        from services.erp.fiscalization_bridge_service import write_back_b2c

        mock_doc_ref = AsyncMock()
        mock_snap = MagicMock()
        mock_snap.exists = True
        mock_snap.to_dict.return_value = {"company_id": "co", "display_id": "RA-001"}
        mock_doc_ref.get = AsyncMock(return_value=mock_snap)

        mock_col = MagicMock()
        mock_col.document.return_value = mock_doc_ref
        mock_db = MagicMock()
        mock_db.collection.return_value = mock_col

        with patch("services.erp.fiscalization_bridge_service._db", return_value=mock_db), \
             patch("services.erp.base_erp_service.write_audit", new_callable=AsyncMock):
            await write_back_b2c(
                erp_invoice_id="test-inv-id",
                fiskalizacija_result={
                    "success": True,
                    "jir": "aabbccdd-1234-5678-abcd-ef1234567890",
                    "zki": "ABCDEF1234567890",
                    "verification_url": "https://porezna.gov.hr/rn?jir=aabb",
                    "qr_code_base64": "base64data",
                },
            )

        update_call = mock_doc_ref.update.call_args[0][0]
        assert update_call["fiscalization_status"] == "fiscalized"
        assert update_call["jir"] == "aabbccdd-1234-5678-abcd-ef1234567890"
        assert update_call["fiscalization_error"] is None

    @pytest.mark.asyncio
    async def test_write_back_failure_routes_to_failed_status(self):
        from services.erp.fiscalization_bridge_service import write_back_b2c

        mock_doc_ref = AsyncMock()
        mock_col = MagicMock()
        mock_col.document.return_value = mock_doc_ref
        mock_db = MagicMock()
        mock_db.collection.return_value = mock_col

        with patch("services.erp.fiscalization_bridge_service._db", return_value=mock_db):
            await write_back_b2c(
                erp_invoice_id="inv-fail",
                fiskalizacija_result={"success": False, "jir": None, "error_message": "FINA timeout"},
            )

        update_call = mock_doc_ref.update.call_args[0][0]
        assert update_call["fiscalization_status"] == "fiscalization_failed"
        assert "FINA timeout" in update_call["fiscalization_error"]

    @pytest.mark.asyncio
    async def test_no_op_when_empty_invoice_id(self):
        from services.erp.fiscalization_bridge_service import write_back_b2c
        with patch("services.erp.fiscalization_bridge_service._db") as mock_db:
            await write_back_b2c("", {"success": True, "jir": "x", "zki": "y"})
            mock_db.assert_not_called()

    @pytest.mark.asyncio
    async def test_firestore_error_does_not_propagate(self):
        from services.erp.fiscalization_bridge_service import write_back_b2c

        mock_doc_ref = AsyncMock()
        mock_doc_ref.update = AsyncMock(side_effect=Exception("Firestore unavailable"))
        mock_col = MagicMock()
        mock_col.document.return_value = mock_doc_ref
        mock_db = MagicMock()
        mock_db.collection.return_value = mock_col

        with patch("services.erp.fiscalization_bridge_service._db", return_value=mock_db):
            await write_back_b2c(
                erp_invoice_id="inv-999",
                fiskalizacija_result={"success": True, "jir": "jir-val", "zki": "zki-val"},
            )


# ── C1: B2C fiscalization fields at create time ──────────────────────────────

class TestB2CFiscalizationFieldsOnCreate:

    @pytest.mark.asyncio
    async def test_b2c_invoice_has_pending_fiscalization_status(self, cid):
        from services.erp.quote_service import QuoteService
        from services.erp.customer_service import CustomerService
        from services.erp.base_erp_service import get_firestore_db

        svc = QuoteService()
        ctx = make_ctx(cid)

        cust = await CustomerService().create_customer(
            {"name": "Fisc Test", "oib": "33333333330", "party_type": "customer"}, ctx
        )
        q = await svc.create_quote({
            "customer_id": cust["_id"],
            "customer_name": "Fisc Test", "customer_oib": "33333333330",
            "valid_until": str(date.today()),
            "items": [{"name": "X", "quantity": 1, "unit_price": 100.0, "vat_rate": 25}],
        }, ctx)
        await svc.mark_sent(q["quote_id"], ctx)
        await svc.accept_quote(q["quote_id"], ctx)
        result = await svc.convert_to_invoice(q["quote_id"], "b2c", ctx)

        snap = await get_firestore_db().collection("invoices_b2c").document(result["invoice_id"]).get()
        doc = snap.to_dict() or {}

        assert doc.get("fiscalization_status") == "pending"
        assert doc.get("jir") is None
        assert doc.get("zki") is None
        assert doc.get("fiscalized_at") is None

    @pytest.mark.asyncio
    async def test_non_b2c_invoice_has_not_required_status(self, cid):
        from services.erp.quote_service import QuoteService
        from services.erp.customer_service import CustomerService
        from services.erp.base_erp_service import get_firestore_db

        svc = QuoteService()
        ctx = make_ctx(cid)

        cust = await CustomerService().create_customer(
            {"name": "EU Test", "oib": "44444444440", "party_type": "customer"}, ctx
        )
        q = await svc.create_quote({
            "customer_id": cust["_id"],
            "customer_name": "EU Test", "customer_oib": "44444444440",
            "valid_until": str(date.today()),
            "items": [{"name": "Y", "quantity": 1, "unit_price": 200.0, "vat_rate": 0}],
        }, ctx)
        await svc.mark_sent(q["quote_id"], ctx)
        await svc.accept_quote(q["quote_id"], ctx)
        result = await svc.convert_to_invoice(q["quote_id"], "eu", ctx)

        snap = await get_firestore_db().collection("invoices_eu").document(result["invoice_id"]).get()
        doc = snap.to_dict() or {}
        assert doc.get("fiscalization_status") == "not_required"


