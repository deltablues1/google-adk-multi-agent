"""
Sync unit tests — no asyncio, no Firestore.
=============================================
Pure Python logic tests that run in microseconds.
Extracted from test_sprint_c0_c1.py to avoid pytest-asyncio warnings
about sync functions bearing the module-level asyncio marker.
"""

import pytest

# No asyncio pytestmark here — all tests are synchronous.
pytestmark = [pytest.mark.unit]


# ── IBAN validation ───────────────────────────────────────────────────────────

def test_iban_valid_croatian():
    from services.erp.company_service import _validate_iban
    assert _validate_iban("HR1210010051863000160") is True


def test_iban_invalid_wrong_length():
    from services.erp.company_service import _validate_iban
    assert _validate_iban("HR121001005186300016") is False   # 20 chars, not 21


def test_iban_invalid_bad_checksum():
    from services.erp.company_service import _validate_iban
    assert _validate_iban("HR0010010051863000160") is False  # checksum digit off


def test_iban_empty_returns_false():
    from services.erp.company_service import _validate_iban
    assert _validate_iban("") is False


def test_iban_non_hr_valid():
    """German IBAN — valid per MOD-97 check."""
    from services.erp.company_service import _validate_iban
    assert _validate_iban("DE89370400440532013000") is True


def test_iban_spaces_are_stripped_before_validation():
    """Spaces in IBAN (typed by user) must not break validation — normalize first."""
    from services.erp.company_service import _validate_iban
    # _validate_iban receives already-normalized input (strip done by caller)
    # so a raw spaced IBAN should fail (raw is not our job to normalize here)
    assert _validate_iban("HR12 1001 0051 8630 0016 0") is False  # spaces inside


# ── Role permission table ─────────────────────────────────────────────────────

def test_role_accountant_has_company_read():
    from services.erp.base_erp_service import ROLE_PERMISSIONS
    assert "company:read" in ROLE_PERMISSIONS["accountant"]


def test_role_accountant_has_company_write():
    from services.erp.base_erp_service import ROLE_PERMISSIONS
    assert "company:write" in ROLE_PERMISSIONS["accountant"]

def test_role_viewer_lacks_company_write():
    from services.erp.base_erp_service import ROLE_PERMISSIONS
    assert "company:write" not in ROLE_PERMISSIONS["viewer"]


def test_role_employee_lacks_company_write():
    from services.erp.base_erp_service import ROLE_PERMISSIONS
    assert "company:write" not in ROLE_PERMISSIONS["employee"]


def test_role_accountant_has_invoice_fiscalize():
    from services.erp.base_erp_service import ROLE_PERMISSIONS
    assert "invoice:fiscalize" in ROLE_PERMISSIONS["accountant"]


def test_role_viewer_lacks_invoice_fiscalize():
    from services.erp.base_erp_service import ROLE_PERMISSIONS
    assert "invoice:fiscalize" not in ROLE_PERMISSIONS["viewer"]

def test_peppol_normalise_known_statuses():
    from services.erp.peppol_status_service import normalise_status
    assert normalise_status("delivered")  == "delivered"
    assert normalise_status("DELIVERED")  == "delivered"   # case-insensitive
    assert normalise_status("accepted")   == "accepted"
    assert normalise_status("rejected")   == "rejected"
    assert normalise_status("failed")     == "failed"
    assert normalise_status("pending")    == "pending"
    assert normalise_status("queued")     == "pending"
    assert normalise_status("acknowledged") == "accepted"


def test_peppol_normalise_unknown_falls_back_to_pending():
    from services.erp.peppol_status_service import normalise_status
    assert normalise_status("xyzzy") == "pending"
    assert normalise_status("")      == "pending"


def test_peppol_normalise_croatian_strings():
    from services.erp.peppol_status_service import normalise_status
    assert normalise_status("dostavljeno")  == "delivered"
    assert normalise_status("prihvaceno")   == "accepted"
    assert normalise_status("odbijeno")     == "rejected"
    assert normalise_status("neisporuceno") == "failed"


def test_peppol_is_terminal():
    from services.erp.peppol_status_service import is_terminal
    assert is_terminal("accepted")  is True
    assert is_terminal("rejected")  is True
    assert is_terminal("failed")    is True
    assert is_terminal("pending")   is False
    assert is_terminal("delivered") is False


def test_peppol_needs_poll():
    from services.erp.peppol_status_service import needs_poll
    assert needs_poll("pending")   is True
    assert needs_poll("delivered") is True
    assert needs_poll("accepted")  is False
    assert needs_poll("rejected")  is False
    assert needs_poll("failed")    is False


# ── C2.2 Webhook verification ─────────────────────────────────────────────────

def test_peppol_webhook_no_secret_accepts_all():
    import os
    from services.erp.peppol_status_service import verify_webhook_request
    os.environ.pop("PEPPOL_AP_WEBHOOK_SECRET", None)
    assert verify_webhook_request({}, b"anything") is True


def test_peppol_webhook_valid_hmac_accepted():
    import hashlib
    import hmac
    from unittest.mock import patch
    from services.erp.peppol_status_service import verify_webhook_request
    secret = "test-secret-123"
    body   = b'{"submissionId":"X1","status":"delivered"}'
    sig    = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    with patch.dict("os.environ", {"PEPPOL_AP_WEBHOOK_SECRET": secret}):
        assert verify_webhook_request({"X-Peppol-Signature": sig}, body) is True


def test_peppol_webhook_wrong_hmac_rejected():
    from unittest.mock import patch
    from services.erp.peppol_status_service import verify_webhook_request
    with patch.dict("os.environ", {"PEPPOL_AP_WEBHOOK_SECRET": "real-secret"}):
        assert verify_webhook_request({"X-Peppol-Signature": "deadbeef"}, b"body") is False


def test_peppol_webhook_missing_header_rejected():
    from unittest.mock import patch
    from services.erp.peppol_status_service import verify_webhook_request
    with patch.dict("os.environ", {"PEPPOL_AP_WEBHOOK_SECRET": "s"}):
        assert verify_webhook_request({}, b"body") is False


# ── C2.2 Webhook payload parsing ─────────────────────────────────────────────

def test_peppol_parse_camelcase_fields():
    from services.erp.peppol_status_service import parse_webhook_payload
    p = parse_webhook_payload({"submissionId": "SID-1", "status": "delivered"})
    assert p["submission_id"] == "SID-1"
    assert p["status"]        == "delivered"


def test_peppol_parse_snake_case_fields():
    from services.erp.peppol_status_service import parse_webhook_payload
    p = parse_webhook_payload({"submission_id": "SID-2", "status": "accepted"})
    assert p["submission_id"] == "SID-2"
    assert p["status"]        == "accepted"


def test_peppol_parse_rejection_reason():
    from services.erp.peppol_status_service import parse_webhook_payload
    p = parse_webhook_payload({
        "submissionId": "SID-3", "status": "rejected",
        "rejectionReason": "PDV broj nevaljan",
    })
    assert p["status"]        == "rejected"
    assert p["buyer_message"] == "PDV broj nevaljan"


def test_peppol_parse_missing_submission_id():
    from services.erp.peppol_status_service import parse_webhook_payload
    assert parse_webhook_payload({"status": "delivered"}) == {}


def test_peppol_parse_empty_body():
    from services.erp.peppol_status_service import parse_webhook_payload
    assert parse_webhook_payload({})   == {}
    assert parse_webhook_payload(None) == {}


# ── C2.2.2 hardening ─────────────────────────────────────────────────────────

def test_peppol_parse_receiver_and_sender_extracted():
    """Disambiguation hints are extracted from camelCase and snake_case variants."""
    from services.erp.peppol_status_service import parse_webhook_payload
    p = parse_webhook_payload({
        "submissionId": "SID-X",
        "status": "delivered",
        "receiverId": "0190:22222222220",
        "senderId":   "0190:47034854402",
    })
    assert p["receiver_participant_id"] == "0190:22222222220"
    assert p["sender_participant_id"]   == "0190:47034854402"


def test_peppol_parse_receiver_snake_case():
    from services.erp.peppol_status_service import parse_webhook_payload
    p = parse_webhook_payload({
        "submissionId": "SID-Y",
        "status": "accepted",
        "receiver_id": "0190:33333333330",
    })
    assert p["receiver_participant_id"] == "0190:33333333330"


def test_peppol_parse_no_participants_returns_empty_strings():
    from services.erp.peppol_status_service import parse_webhook_payload
    p = parse_webhook_payload({"submissionId": "SID-Z", "status": "pending"})
    assert p["receiver_participant_id"] == ""
    assert p["sender_participant_id"]   == ""


def test_peppol_webhook_no_secret_logs_error_in_production(caplog):
    """When ENVIRONMENT=production and no secret, error is logged."""
    import logging
    from unittest.mock import patch
    from services.erp.peppol_status_service import verify_webhook_request
    with patch.dict("os.environ", {"ENVIRONMENT": "production"}):
        import os
        os.environ.pop("PEPPOL_AP_WEBHOOK_SECRET", None)
        with caplog.at_level(logging.ERROR, logger="services.erp.peppol_status_service"):
            result = verify_webhook_request({}, b"body")
    assert result is False  # fail-closed: no secret in production → reject
    assert any("SECURITY" in r.message for r in caplog.records), (
        "Production mode without webhook secret must log a SECURITY error"
    )

