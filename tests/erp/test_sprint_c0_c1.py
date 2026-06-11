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


@pytest.mark.unit
class TestFiscalizeB2CService:

    @pytest.mark.asyncio
    async def test_already_fiscalized_returns_cached(self):
        from services.erp.fiscalization_bridge_service import fiscalize_b2c_invoice

        mock_snap = MagicMock()
        mock_snap.exists = True
        mock_snap.to_dict.return_value = {
            "fiscalization_status": "fiscalized",
            "jir": "aabb-ccdd",
            "zki": "AABB1234",
            "fiscalized_at": "2026-01-01T10:00:00+00:00",
            "verification_url": "https://porezna.gov.hr/rn?jir=aabb",
        }
        mock_doc_ref = AsyncMock()
        mock_doc_ref.get = AsyncMock(return_value=mock_snap)
        mock_col = MagicMock()
        mock_col.document.return_value = mock_doc_ref
        mock_db = MagicMock()
        mock_db.collection.return_value = mock_col

        with patch("services.erp.fiscalization_bridge_service._db", return_value=mock_db):
            result = await fiscalize_b2c_invoice("inv-already", make_ctx("co1"))

        assert result["already_fiscalized"] is True
        assert result["jir"] == "aabb-ccdd"
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_not_found_raises(self):
        from services.erp.fiscalization_bridge_service import fiscalize_b2c_invoice
        from services.erp.errors import NotFoundError

        mock_snap = MagicMock()
        mock_snap.exists = False
        mock_doc_ref = AsyncMock()
        mock_doc_ref.get = AsyncMock(return_value=mock_snap)
        mock_col = MagicMock()
        mock_col.document.return_value = mock_doc_ref
        mock_db = MagicMock()
        mock_db.collection.return_value = mock_col

        with patch("services.erp.fiscalization_bridge_service._db", return_value=mock_db):
            with pytest.raises(NotFoundError):
                await fiscalize_b2c_invoice("nonexistent", make_ctx("co1"))

    @pytest.mark.asyncio
    async def test_wrong_status_raises_validation_error(self):
        from services.erp.fiscalization_bridge_service import fiscalize_b2c_invoice
        from services.erp.errors import ValidationError

        mock_snap = MagicMock()
        mock_snap.exists = True
        mock_snap.to_dict.return_value = {"fiscalization_status": "not_required"}
        mock_doc_ref = AsyncMock()
        mock_doc_ref.get = AsyncMock(return_value=mock_snap)
        mock_col = MagicMock()
        mock_col.document.return_value = mock_doc_ref
        mock_db = MagicMock()
        mock_db.collection.return_value = mock_col

        with patch("services.erp.fiscalization_bridge_service._db", return_value=mock_db):
            with pytest.raises(ValidationError) as exc_info:
                await fiscalize_b2c_invoice("inv-not-required", make_ctx("co1"))
        assert exc_info.value.code == "INVALID_FISCALIZATION_STATE"

    @pytest.mark.asyncio
    async def test_insufficient_permission_raises(self):
        from services.erp.fiscalization_bridge_service import fiscalize_b2c_invoice
        from services.erp.errors import InsufficientPermissionError
        ctx_viewer = make_ctx("co1", "viewer")
        with pytest.raises(InsufficientPermissionError):
            await fiscalize_b2c_invoice("inv-any", ctx_viewer)


# ── C1.1: API routes ──────────────────────────────────────────────────────────

class TestFiscalizeB2CAPI:

    @pytest.fixture(scope="class")
    def company_id(self):
        return f"test_c1_api_{uuid4().hex}"

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
                content={"code": exc.code, "message": exc.message},
            )

        app.include_router(erp_router)

        def _ctx():
            return ERPRequestContext(
                user_id="test-fisc-api", company_id=company_id,
                role="owner", grants=["*"], denies=[], request_id=str(uuid4()),
            )

        app.dependency_overrides[get_erp_ctx] = _ctx
        return app

    @pytest.mark.asyncio
    async def test_fiscalization_status_of_pending_invoice(self, app, company_id):
        """After converting a quote to B2C invoice, the status endpoint returns pending."""
        from httpx import AsyncClient, ASGITransport
        from services.erp.quote_service import QuoteService
        from services.erp.customer_service import CustomerService

        ctx = make_ctx(company_id)
        cust = await CustomerService().create_customer(
            {"name": "API Fisc Test", "oib": "55555555550", "party_type": "customer"}, ctx
        )
        q = await QuoteService().create_quote({
            "customer_id": cust["_id"],
            "customer_name": "API Fisc Test", "customer_oib": "55555555550",
            "valid_until": str(date.today()),
            "items": [{"name": "Z", "quantity": 1, "unit_price": 100.0, "vat_rate": 25}],
        }, ctx)
        await QuoteService().mark_sent(q["quote_id"], ctx)
        await QuoteService().accept_quote(q["quote_id"], ctx)
        result = await QuoteService().convert_to_invoice(q["quote_id"], "b2c", ctx)
        invoice_id = result["invoice_id"]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get(f"/api/erp/invoices/b2c/{invoice_id}/fiscalization-status")
        assert r.status_code == 200
        body = r.json()
        assert body.get("fiscalization_status") == "pending"
        assert body.get("jir") is None

    @pytest.mark.asyncio
    async def test_fiscalize_route_returns_error_without_cert(self, app, company_id):
        """Without a real FINA cert, fiscalize returns 200 with success=False (non-raising)."""
        from httpx import AsyncClient, ASGITransport
        from services.erp.quote_service import QuoteService
        from services.erp.customer_service import CustomerService

        ctx = make_ctx(company_id)
        cust = await CustomerService().create_customer(
            {"name": "NoCert Test", "oib": "66666666660", "party_type": "customer"}, ctx
        )
        q = await QuoteService().create_quote({
            "customer_id": cust["_id"],
            "customer_name": "NoCert Test", "customer_oib": "66666666660",
            "valid_until": str(date.today()),
            "items": [{"name": "Q", "quantity": 1, "unit_price": 50.0, "vat_rate": 25}],
        }, ctx)
        await QuoteService().mark_sent(q["quote_id"], ctx)
        await QuoteService().accept_quote(q["quote_id"], ctx)
        result = await QuoteService().convert_to_invoice(q["quote_id"], "b2c", ctx)
        invoice_id = result["invoice_id"]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(f"/api/erp/invoices/b2c/{invoice_id}/fiscalize")

        # Without a real certificate, execute_fiscalization() returns success=False
        # but the route itself must not 500.
        assert r.status_code == 200
        body = r.json()
        assert "success" in body

    @pytest.mark.asyncio
    async def test_fiscalize_already_fiscalized_is_idempotent(self, app, company_id):
        """Calling fiscalize on an already-fiscalized invoice returns cached data, not 4xx."""
        from httpx import AsyncClient, ASGITransport
        from services.erp.fiscalization_bridge_service import write_back_b2c
        from services.erp.quote_service import QuoteService
        from services.erp.customer_service import CustomerService

        ctx = make_ctx(company_id)
        cust = await CustomerService().create_customer(
            {"name": "Idem Test", "oib": "77777777770", "party_type": "customer"}, ctx
        )
        q = await QuoteService().create_quote({
            "customer_id": cust["_id"],
            "customer_name": "Idem Test", "customer_oib": "77777777770",
            "valid_until": str(date.today()),
            "items": [{"name": "W", "quantity": 1, "unit_price": 80.0, "vat_rate": 25}],
        }, ctx)
        await QuoteService().mark_sent(q["quote_id"], ctx)
        await QuoteService().accept_quote(q["quote_id"], ctx)
        result = await QuoteService().convert_to_invoice(q["quote_id"], "b2c", ctx)
        invoice_id = result["invoice_id"]

        # Manually write a fiscalized state (simulate successful CIS response)
        await write_back_b2c(
            erp_invoice_id=invoice_id,
            fiskalizacija_result={
                "success": True,
                "jir": "test-jir-idem-0001",
                "zki": "TESTZKI0001",
                "verification_url": "https://porezna.gov.hr/rn?jir=test",
                "qr_code_base64": None,
            },
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(f"/api/erp/invoices/b2c/{invoice_id}/fiscalize")

        assert r.status_code == 200
        body = r.json()
        assert body["already_fiscalized"] is True
        assert body["jir"] == "test-jir-idem-0001"


# ── C1.2: ERP display_id vs fiscal_invoice_number separation ─────────────────

@pytest.mark.unit
class TestFiscalInvoiceNumberSeparation:
    """
    Regression lock: ERP display_id (RA-...) must never be sent to FINA.
    fiscal_invoice_number (XXX/PP/NU) is the FINA-required number.
    """

    @pytest.mark.asyncio
    async def test_b2c_invoice_has_fiscal_fields_on_create(self, cid):
        """B2C invoice created from quote must have fiscal fields (null at creation)."""
        from services.erp.quote_service import QuoteService
        from services.erp.customer_service import CustomerService
        from services.erp.base_erp_service import get_firestore_db

        ctx = make_ctx(cid)
        cust = await CustomerService().create_customer(
            {"name": "Fiscal Sep", "oib": "88888888880", "party_type": "customer"}, ctx
        )
        q = await QuoteService().create_quote({
            "customer_id": cust["_id"],
            "customer_name": "Fiscal Sep", "customer_oib": "88888888880",
            "valid_until": str(date.today()),
            "items": [{"name": "A", "quantity": 1, "unit_price": 100.0, "vat_rate": 25}],
        }, ctx)
        await QuoteService().mark_sent(q["quote_id"], ctx)
        await QuoteService().accept_quote(q["quote_id"], ctx)
        result = await QuoteService().convert_to_invoice(q["quote_id"], "b2c", ctx)
        invoice_id = result["invoice_id"]

        snap = await get_firestore_db().collection("invoices_b2c").document(invoice_id).get()
        doc = snap.to_dict() or {}

        # ERP number is RA-... format
        assert doc.get("display_id", "").startswith("RA-"), (
            f"display_id must start with RA-, got: {doc.get('display_id')}"
        )
        # Fiscal number fields exist but are null at creation time
        assert "fiscal_invoice_number" in doc, "fiscal_invoice_number field must exist at creation"
        assert doc["fiscal_invoice_number"] is None, (
            "fiscal_invoice_number must be None at creation time — set at fiscalization"
        )
        assert "business_unit" in doc
        assert "device_number" in doc

    @pytest.mark.asyncio
    async def test_fiscal_number_is_fina_format_not_erp_display_id(self):
        """After write_back_b2c with fiscal_invoice_number, the field has XXX/PP/NU format."""
        from services.erp.fiscalization_bridge_service import write_back_b2c

        mock_doc_ref = AsyncMock()
        mock_snap = MagicMock()
        mock_snap.exists = True
        mock_snap.to_dict.return_value = {"company_id": "co1", "display_id": "RA-2026-001"}
        mock_doc_ref.get = AsyncMock(return_value=mock_snap)

        mock_col = MagicMock()
        mock_col.document.return_value = mock_doc_ref
        mock_db = MagicMock()
        mock_db.collection.return_value = mock_col

        fiskalizacija_result = {
            "success":               True,
            "jir":                   "deadbeef-1111-2222-3333-444455556666",
            "zki":                   "DEADBEEF1234567890",
            "verification_url":      "https://porezna.gov.hr/rn?jir=dead",
            "qr_code_base64":        None,
            "fiscal_invoice_number": "7/1/1",  # FINA number — NOT RA-...
        }

        with patch("services.erp.fiscalization_bridge_service._db", return_value=mock_db), \
             patch("services.erp.base_erp_service.write_audit", new_callable=AsyncMock):
            await write_back_b2c("inv-sep-test", fiskalizacija_result)

        update_call = mock_doc_ref.update.call_args[0][0]
        assert update_call["fiscalization_status"] == "fiscalized"
        assert update_call.get("fiscal_invoice_number") == "7/1/1", (
            "write_back_b2c must persist fiscal_invoice_number from result"
        )
        # The ERP display_id was NOT modified — only fiscal fields changed
        assert "display_id" not in update_call, (
            "write_back_b2c must NOT overwrite display_id"
        )

    @pytest.mark.asyncio
    async def test_get_supplier_data_prefers_company_settings(self, cid):
        """get_supplier_data(company_id=...) returns vu_code/nu_code from company_settings."""
        from tools.adk_tools.fiskalizacija_adk_tools import get_supplier_data
        from services.erp.company_service import get_company_service

        ctx = make_ctx(cid, "owner")
        # Store company_settings with fiscal codes
        await get_company_service().upsert({
            "oib":  "47034854402",
            "name": "Fiscal Source Test d.o.o.",
            "vu_code": "PP1",
            "nu_code": "NU2",
        }, ctx)

        result = await get_supplier_data(company_id=cid)

        assert result["success"] is True
        assert result["source"] == "company_settings"
        assert result["supplier"]["oib"] == "47034854402"
        assert result["supplier"]["business_unit"] == "PP1", (
            "business_unit must come from vu_code in company_settings"
        )
        assert result["supplier"]["device_number"] == "NU2", (
            "device_number must come from nu_code in company_settings"
        )

    @pytest.mark.asyncio
    async def test_get_supplier_data_falls_back_to_company_config(self):
        """get_supplier_data() without company_id falls back to company_config."""
        from tools.adk_tools.fiskalizacija_adk_tools import get_supplier_data
        result = await get_supplier_data()  # no company_id
        # Should succeed via company_config (LUX_TECH_CONFIG)
        assert result["success"] is True
        assert result["source"] == "company_config"
        assert result["supplier"]["oib"] == "47034854402"

    @pytest.mark.asyncio
    async def test_fiscal_number_reused_on_retry(self):
        """fiscalize_b2c_invoice() reuses existing fiscal_invoice_number on retry."""
        from services.erp.fiscalization_bridge_service import fiscalize_b2c_invoice

        # Simulate a fiscalization_failed invoice that already has fiscal_invoice_number
        existing_fiscal_num = "3/PP1/NU2"
        mock_snap = MagicMock()
        mock_snap.exists = True
        mock_snap.to_dict.return_value = {
            "fiscalization_status":  "fiscalization_failed",
            "fiscal_invoice_number": existing_fiscal_num,
            "business_unit":         "PP1",
            "device_number":         "NU2",
            "customer_oib":          "11111111110",
            "customer_name":         "Test Kupac",
            "items": [{"name": "X", "quantity": 1, "unit_price": 100.0, "vat_rate": 25}],
            "created_at":            "2026-04-10T10:00:00+00:00",
        }
        mock_doc_ref = AsyncMock()
        mock_doc_ref.get = AsyncMock(return_value=mock_snap)
        mock_col = MagicMock()
        mock_col.document.return_value = mock_doc_ref
        mock_db = MagicMock()
        mock_db.collection.return_value = mock_col

        captured_payload = {}

        async def mock_execute(payload, *, skip_hitl=False):
            captured_payload.update(payload)
            return {
                "success": False,
                "status": "config_error",
                "error_message": "no cert in test",
                "jir": None,
                "zki": None,
            }

        # get_supplier_data and execute_fiscalization are imported inside the function,
        # so patch the originals in their own modules.
        with patch("services.erp.fiscalization_bridge_service._db", return_value=mock_db), \
             patch(
                 "tools.adk_tools.fiskalizacija_adk_tools.get_supplier_data",
                 new_callable=AsyncMock,
                 return_value={"success": True, "supplier": {
                     "oib": "47034854402", "name": "Test", "address": "",
                     "city": "", "business_unit": "PP1", "device_number": "NU2",
                 }},
             ), \
             patch(
                 "tools.adk_tools.fiskalizacija_adk_tools.execute_fiscalization",
                 side_effect=mock_execute,
             ):
            result = await fiscalize_b2c_invoice("inv-retry", make_ctx("co1"))

        # The SAME fiscal_invoice_number must be reused — no new number generated
        assert captured_payload.get("invoice_number") == existing_fiscal_num, (
            f"Retry must reuse fiscal_invoice_number={existing_fiscal_num}, "
            f"got {captured_payload.get('invoice_number')}"
        )
        # ERP display_id must NOT be sent to FINA
        assert captured_payload.get("invoice_number", "").startswith("RA-") is False

        # Result should expose fiscal_invoice_number
        assert result["fiscal_invoice_number"] == existing_fiscal_num


# ── C1.2: company_settings as canonical supplier source — API test ────────────

class TestSupplierSourceAPI:

    @pytest.fixture(scope="class")
    def company_id(self):
        return f"test_c12_api_{uuid4().hex}"

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
                content={"code": exc.code, "message": exc.message},
            )

        app.include_router(erp_router)

        def _ctx():
            return ERPRequestContext(
                user_id="test-c12-api", company_id=company_id,
                role="owner", grants=["*"], denies=[], request_id=str(uuid4()),
            )

        app.dependency_overrides[get_erp_ctx] = _ctx
        return app

    @pytest.mark.asyncio
    async def test_fiscal_fields_present_in_invoice_after_create(self, app, company_id):
        """GET /invoices/b2c/{id} returns fiscal_invoice_number field (null at creation)."""
        from httpx import AsyncClient, ASGITransport
        from services.erp.quote_service import QuoteService
        from services.erp.customer_service import CustomerService

        ctx = make_ctx(company_id)
        cust = await CustomerService().create_customer(
            {"name": "API Src Test", "oib": "99999999990", "party_type": "customer"}, ctx
        )
        q = await QuoteService().create_quote({
            "customer_id": cust["_id"],
            "customer_name": "API Src Test", "customer_oib": "99999999990",
            "valid_until": str(date.today()),
            "items": [{"name": "B", "quantity": 1, "unit_price": 200.0, "vat_rate": 25}],
        }, ctx)
        await QuoteService().mark_sent(q["quote_id"], ctx)
        await QuoteService().accept_quote(q["quote_id"], ctx)
        result = await QuoteService().convert_to_invoice(q["quote_id"], "b2c", ctx)
        invoice_id = result["invoice_id"]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get(f"/api/erp/invoices/b2c/{invoice_id}")

        assert r.status_code == 200
        body = r.json()
        # ERP number is preserved
        assert body.get("display_id", "").startswith("RA-")
        # fiscal_invoice_number field is present (null until fiscalization)
        assert "fiscal_invoice_number" in body
        assert body["fiscal_invoice_number"] is None
