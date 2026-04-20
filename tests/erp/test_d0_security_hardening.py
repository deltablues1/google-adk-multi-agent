"""
Sprint D0 — Tenant and security hardening tests
=================================================
Covers:
  - company_service: peppol_participant_id uniqueness (upsert + patch)
  - peppol_status_service.verify_webhook_request: fail-closed in prod/staging
  - inbound_peppol_transport_service.verify_inbound_webhook: fail-closed in prod/staging
"""

import hashlib
import hmac
import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from uuid import uuid4

from services.erp.request_context import ERPRequestContext
from services.erp.errors import ValidationError

# File-level mark: integration only — no asyncio here, as two of the three test
# classes are fully synchronous.  The async class sets its own asyncio mark below.
pytestmark = [pytest.mark.integration]


def _ctx(company_id: str = None) -> ERPRequestContext:
    return ERPRequestContext(
        user_id="test-d0",
        company_id=company_id or f"co-{uuid4().hex[:8]}",
        role="owner",
        grants=["*"],
        denies=[],
        request_id=str(uuid4()),
    )


# ---------------------------------------------------------------------------
# Helpers — minimal Firestore mocks
# ---------------------------------------------------------------------------

def _make_snap(doc_id: str, data: dict):
    snap = MagicMock()
    snap.id = doc_id
    snap.exists = True
    snap.to_dict.return_value = data
    return snap


def _async_stream(*snaps):
    """Return an async generator yielding the given snapshots."""
    async def _gen():
        for s in snaps:
            yield s
    return _gen()


# ---------------------------------------------------------------------------
# peppol_participant_id uniqueness — upsert
# ---------------------------------------------------------------------------

@pytest.mark.asyncio(loop_scope="session")
class TestPeppolParticipantIdUniqueness:
    """company_service.CompanyService._assert_peppol_id_unique"""

    async def test_upsert_accepts_unique_peppol_id(self):
        """No conflict → upsert succeeds and returns doc with peppol_participant_id."""
        from services.erp.company_service import CompanyService
        svc = CompanyService()
        ctx = _ctx("co-alpha")

        mock_doc_ref = MagicMock()
        mock_existing_snap = MagicMock(exists=False)

        # The uniqueness query returns no matching docs (empty stream)
        mock_query = MagicMock()
        mock_query.stream.return_value = _async_stream()

        mock_col = MagicMock()
        mock_col.where.return_value = mock_query  # chained .limit() returns same mock
        mock_query.limit.return_value = mock_query

        mock_db = MagicMock()
        mock_db.collection.return_value = mock_col
        mock_col.document.return_value = mock_doc_ref
        mock_doc_ref.get = AsyncMock(return_value=mock_existing_snap)
        mock_doc_ref.set = AsyncMock()

        with patch.object(svc, "_get_db", return_value=mock_db), \
             patch("services.erp.company_service.write_audit", AsyncMock()):
            result = await svc.upsert(
                {"name": "Alpha d.o.o.", "peppol_participant_id": "0190:12345678901"},
                ctx,
            )

        assert result["peppol_participant_id"] == "0190:12345678901"

    async def test_upsert_rejects_duplicate_peppol_id_different_company(self):
        """Same Peppol ID already registered for a different company → ValidationError."""
        from services.erp.company_service import CompanyService
        svc = CompanyService()
        ctx = _ctx("co-beta")

        # The uniqueness query returns one doc from a *different* company
        conflict_snap = _make_snap("co-gamma", {"peppol_participant_id": "0190:99999999999"})

        mock_query = MagicMock()
        mock_query.stream.return_value = _async_stream(conflict_snap)
        mock_query.limit.return_value = mock_query

        mock_col = MagicMock()
        mock_col.where.return_value = mock_query

        mock_db = MagicMock()
        mock_db.collection.return_value = mock_col

        with patch.object(svc, "_get_db", return_value=mock_db):
            with pytest.raises(ValidationError) as exc_info:
                await svc.upsert(
                    {"peppol_participant_id": "0190:99999999999"},
                    ctx,
                )

        err = exc_info.value
        assert err.code == "PEPPOL_ID_CONFLICT"
        assert "0190:99999999999" in err.message
        assert err.field == "peppol_participant_id"

    async def test_upsert_allows_same_id_for_same_company(self):
        """
        Upserting the same Peppol ID that the company already owns must not raise.
        The query returns a snap with the *same* company_id → not a conflict.
        """
        from services.erp.company_service import CompanyService
        svc = CompanyService()
        ctx = _ctx("co-delta")

        # Query returns the same company's own doc
        own_snap = _make_snap("co-delta", {"peppol_participant_id": "0190:11111111111"})

        mock_query = MagicMock()
        mock_query.stream.return_value = _async_stream(own_snap)
        mock_query.limit.return_value = mock_query

        mock_doc_ref = MagicMock()
        mock_existing_snap = MagicMock(exists=False)
        mock_doc_ref.get = AsyncMock(return_value=mock_existing_snap)
        mock_doc_ref.set = AsyncMock()

        mock_col = MagicMock()
        mock_col.where.return_value = mock_query
        mock_col.document.return_value = mock_doc_ref

        mock_db = MagicMock()
        mock_db.collection.return_value = mock_col

        with patch.object(svc, "_get_db", return_value=mock_db), \
             patch("services.erp.company_service.write_audit", AsyncMock()):
            result = await svc.upsert(
                {"peppol_participant_id": "0190:11111111111"},
                ctx,
            )
        assert result["peppol_participant_id"] == "0190:11111111111"

    async def test_upsert_empty_peppol_id_skips_uniqueness_check(self):
        """Empty peppol_participant_id → no query, no conflict."""
        from services.erp.company_service import CompanyService
        svc = CompanyService()
        ctx = _ctx("co-epsilon")

        mock_doc_ref = MagicMock()
        mock_existing_snap = MagicMock(exists=False)
        mock_doc_ref.get = AsyncMock(return_value=mock_existing_snap)
        mock_doc_ref.set = AsyncMock()

        mock_col = MagicMock()
        mock_col.document.return_value = mock_doc_ref

        mock_db = MagicMock()
        mock_db.collection.return_value = mock_col

        with patch.object(svc, "_get_db", return_value=mock_db), \
             patch("services.erp.company_service.write_audit", AsyncMock()):
            result = await svc.upsert({"name": "NoID Corp"}, ctx)

        assert result["peppol_participant_id"] == ""
        # Ensure the uniqueness query was NOT called (collection.where never called)
        mock_col.where.assert_not_called()

    async def test_patch_rejects_duplicate_peppol_id(self):
        """PATCH with a conflicting peppol_participant_id → ValidationError."""
        from services.erp.company_service import CompanyService
        svc = CompanyService()
        ctx = _ctx("co-zeta")

        conflict_snap = _make_snap("co-eta", {"peppol_participant_id": "0190:77777777777"})

        mock_query = MagicMock()
        mock_query.stream.return_value = _async_stream(conflict_snap)
        mock_query.limit.return_value = mock_query

        mock_col = MagicMock()
        mock_col.where.return_value = mock_query

        mock_db = MagicMock()
        mock_db.collection.return_value = mock_col

        with patch.object(svc, "_get_db", return_value=mock_db):
            with pytest.raises(ValidationError) as exc_info:
                await svc.patch(
                    {"peppol_participant_id": "0190:77777777777"},
                    ctx,
                )

        assert exc_info.value.code == "PEPPOL_ID_CONFLICT"

    async def test_patch_skips_check_when_peppol_id_not_in_payload(self):
        """PATCH without peppol_participant_id key → uniqueness check not called."""
        from services.erp.company_service import CompanyService
        svc = CompanyService()
        ctx = _ctx("co-theta")

        existing_snap = _make_snap("co-theta", {"name": "Theta d.o.o.", "created_at": "2026-01-01T00:00:00+00:00"})
        mock_doc_ref = MagicMock()
        mock_doc_ref.get = AsyncMock(return_value=existing_snap)
        mock_doc_ref.update = AsyncMock()

        # get() after update — returns updated doc
        get_snap = _make_snap("co-theta", {"name": "Theta updated", "_id": "co-theta"})
        mock_get_snap = _make_snap("co-theta", {"name": "Theta updated"})
        mock_get_snap.exists = True

        mock_col = MagicMock()
        mock_col.document.return_value = mock_doc_ref

        mock_db = MagicMock()
        mock_db.collection.return_value = mock_col

        with patch.object(svc, "_get_db", return_value=mock_db), \
             patch("services.erp.company_service.write_audit", AsyncMock()), \
             patch.object(svc, "get", AsyncMock(return_value={"name": "Theta updated"})):
            result = await svc.patch({"name": "Theta updated"}, ctx)

        assert result["name"] == "Theta updated"
        mock_col.where.assert_not_called()

class TestOutboundWebhookVerifyFailClosed:
    """peppol_status_service.verify_webhook_request"""

    def test_dev_no_secret_accepts(self):
        """No secret in development mode → True (backward compat)."""
        from services.erp.peppol_status_service import verify_webhook_request
        with patch.dict(os.environ, {"PEPPOL_AP_WEBHOOK_SECRET": "", "ENVIRONMENT": "development"}):
            assert verify_webhook_request({}, b"body") is True

    def test_prod_no_secret_rejects(self):
        """No secret in production → False (fail-closed)."""
        from services.erp.peppol_status_service import verify_webhook_request
        with patch.dict(os.environ, {"PEPPOL_AP_WEBHOOK_SECRET": "", "ENVIRONMENT": "production"}):
            assert verify_webhook_request({}, b"body") is False

    def test_staging_no_secret_rejects(self):
        """No secret in staging → False (fail-closed)."""
        from services.erp.peppol_status_service import verify_webhook_request
        with patch.dict(os.environ, {"PEPPOL_AP_WEBHOOK_SECRET": "", "ENVIRONMENT": "staging"}):
            assert verify_webhook_request({}, b"body") is False

    def test_prod_no_secret_rejects_alias_prod(self):
        """ENVIRONMENT='prod' (short alias) also fails closed."""
        from services.erp.peppol_status_service import verify_webhook_request
        with patch.dict(os.environ, {"PEPPOL_AP_WEBHOOK_SECRET": "", "ENVIRONMENT": "prod"}):
            assert verify_webhook_request({}, b"body") is False

    def test_prod_valid_hmac_accepts(self):
        """Valid HMAC in production → True."""
        from services.erp.peppol_status_service import verify_webhook_request
        secret = "test-secret-xyz"
        body = b'{"event":"status_update"}'
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        with patch.dict(os.environ, {"PEPPOL_AP_WEBHOOK_SECRET": secret, "ENVIRONMENT": "production"}):
            assert verify_webhook_request({"X-Peppol-Signature": sig}, body) is True

    def test_prod_invalid_hmac_rejects(self):
        """Invalid HMAC in production → False."""
        from services.erp.peppol_status_service import verify_webhook_request
        secret = "test-secret-xyz"
        body = b'{"event":"status_update"}'
        with patch.dict(os.environ, {"PEPPOL_AP_WEBHOOK_SECRET": secret, "ENVIRONMENT": "production"}):
            assert verify_webhook_request({"X-Peppol-Signature": "badhash"}, body) is False

    def test_prod_missing_signature_header_rejects(self):
        """Secret set but no signature header in production → False."""
        from services.erp.peppol_status_service import verify_webhook_request
        with patch.dict(os.environ, {"PEPPOL_AP_WEBHOOK_SECRET": "real-secret", "ENVIRONMENT": "production"}):
            assert verify_webhook_request({}, b"body") is False


# ---------------------------------------------------------------------------
# Inbound webhook verification — fail-closed in prod/staging
# ---------------------------------------------------------------------------

class TestInboundWebhookVerifyFailClosed:
    """inbound_peppol_transport_service.verify_inbound_webhook"""

    def test_dev_no_secret_accepts(self):
        """No secret in development mode → True."""
        from services.erp.inbound_peppol_transport_service import verify_inbound_webhook
        with patch.dict(os.environ, {
            "PEPPOL_AP_INBOUND_WEBHOOK_SECRET": "",
            "PEPPOL_AP_WEBHOOK_SECRET": "",
            "ENVIRONMENT": "development",
        }):
            assert verify_inbound_webhook({}, b"body") is True

    def test_prod_no_secret_rejects(self):
        """No secret in production → False (fail-closed)."""
        from services.erp.inbound_peppol_transport_service import verify_inbound_webhook
        with patch.dict(os.environ, {
            "PEPPOL_AP_INBOUND_WEBHOOK_SECRET": "",
            "PEPPOL_AP_WEBHOOK_SECRET": "",
            "ENVIRONMENT": "production",
        }):
            assert verify_inbound_webhook({}, b"body") is False

    def test_staging_no_secret_rejects(self):
        """No secret in staging → False."""
        from services.erp.inbound_peppol_transport_service import verify_inbound_webhook
        with patch.dict(os.environ, {
            "PEPPOL_AP_INBOUND_WEBHOOK_SECRET": "",
            "PEPPOL_AP_WEBHOOK_SECRET": "",
            "ENVIRONMENT": "staging",
        }):
            assert verify_inbound_webhook({}, b"body") is False

    def test_prod_fallback_to_shared_secret(self):
        """
        PEPPOL_AP_INBOUND_WEBHOOK_SECRET not set, but PEPPOL_AP_WEBHOOK_SECRET is →
        use fallback secret for verification.
        """
        from services.erp.inbound_peppol_transport_service import verify_inbound_webhook
        secret = "shared-secret-abc"
        body = b'{"submissionId":"S-001"}'
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        with patch.dict(os.environ, {
            "PEPPOL_AP_INBOUND_WEBHOOK_SECRET": "",
            "PEPPOL_AP_WEBHOOK_SECRET": secret,
            "ENVIRONMENT": "production",
        }):
            assert verify_inbound_webhook({"X-Peppol-Signature": sig}, body) is True

    def test_prod_inbound_specific_secret_takes_precedence(self):
        """PEPPOL_AP_INBOUND_WEBHOOK_SECRET takes precedence over shared secret."""
        from services.erp.inbound_peppol_transport_service import verify_inbound_webhook
        inbound_secret = "inbound-only-secret"
        shared_secret = "shared-secret"
        body = b'{"submissionId":"S-002"}'
        # Sign with inbound-only secret
        sig = hmac.new(inbound_secret.encode(), body, hashlib.sha256).hexdigest()
        with patch.dict(os.environ, {
            "PEPPOL_AP_INBOUND_WEBHOOK_SECRET": inbound_secret,
            "PEPPOL_AP_WEBHOOK_SECRET": shared_secret,
            "ENVIRONMENT": "production",
        }):
            assert verify_inbound_webhook({"X-Peppol-Signature": sig}, body) is True

    def test_prod_missing_signature_header_rejects(self):
        """Secret set, no header in production → False."""
        from services.erp.inbound_peppol_transport_service import verify_inbound_webhook
        with patch.dict(os.environ, {
            "PEPPOL_AP_INBOUND_WEBHOOK_SECRET": "real-secret",
            "PEPPOL_AP_WEBHOOK_SECRET": "",
            "ENVIRONMENT": "production",
        }):
            assert verify_inbound_webhook({}, b"body") is False
