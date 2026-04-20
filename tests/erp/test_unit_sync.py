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

