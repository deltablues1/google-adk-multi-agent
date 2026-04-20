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
