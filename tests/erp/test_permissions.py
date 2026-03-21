"""
Permission Unit Tests
=====================
Pure unit tests — no Firestore, no external services.
Tests check_permission() with all roles and edge cases.

Reflects the ACTUAL ROLE_PERMISSIONS in base_erp_service.py after Bug 5 fix.
accountant CAN approve vendor invoices (that is a business decision, not a bug).
"""

import pytest
from uuid import uuid4

from services.erp.base_erp_service import check_permission
from services.erp.errors import InsufficientPermissionError
from services.erp.request_context import ERPRequestContext


def ctx(role: str, grants: set = None, denies: set = None) -> ERPRequestContext:
    return ERPRequestContext(
        user_id="test",
        company_id="test-company",
        role=role,
        grants=grants or set(),
        denies=denies or set(),
        request_id=str(uuid4()),
    )


# ---------------------------------------------------------------------------
# Owner — wildcard
# ---------------------------------------------------------------------------

class TestOwnerPermissions:

    @pytest.mark.parametrize("permission", [
        "invoice:read", "invoice:create",
        "payment:record",
        "vendor_invoice:approve",
        "product:write", "stock:adjust",
        "report:read",
        "some:future:permission",  # owner wildcard covers everything
    ])
    def test_owner_can_do_everything(self, permission):
        check_permission(ctx("owner"), permission)  # should not raise


# ---------------------------------------------------------------------------
# Accountant
# ---------------------------------------------------------------------------

class TestAccountantPermissions:

    @pytest.mark.parametrize("permission", [
        "invoice:read", "invoice:create",
        "payment:record",
        "vendor_invoice:read", "vendor_invoice:approve",
        "customer:read", "customer:create", "customer:update",
        "product:read", "product:write", "stock:adjust",
        "report:read",
        "expense:read",
        "quote:read", "quote:create", "quote:update", "quote:send", "quote:convert",
    ])
    def test_accountant_allowed(self, permission):
        check_permission(ctx("accountant"), permission)  # should not raise

    @pytest.mark.parametrize("permission", [
        "vendor_invoice:create",  # accountant doesn't create, employee does
        "expense:create",
        "some:admin:permission",
    ])
    def test_accountant_forbidden(self, permission):
        with pytest.raises(InsufficientPermissionError):
            check_permission(ctx("accountant"), permission)


# ---------------------------------------------------------------------------
# Employee
# ---------------------------------------------------------------------------

class TestEmployeePermissions:

    @pytest.mark.parametrize("permission", [
        "invoice:read",
        "vendor_invoice:read", "vendor_invoice:create",
        "expense:create",
        "customer:read",
        "product:read", "stock:adjust",
        "quote:read", "quote:create", "quote:update", "quote:send",
    ])
    def test_employee_allowed(self, permission):
        check_permission(ctx("employee"), permission)  # should not raise

    @pytest.mark.parametrize("permission", [
        "payment:record",
        "vendor_invoice:approve",
        "product:write",
        "report:read",
        "invoice:create",
        "quote:convert",
    ])
    def test_employee_forbidden(self, permission):
        with pytest.raises(InsufficientPermissionError):
            check_permission(ctx("employee"), permission)


# ---------------------------------------------------------------------------
# Viewer
# ---------------------------------------------------------------------------

class TestViewerPermissions:

    @pytest.mark.parametrize("permission", [
        "invoice:read",
        "vendor_invoice:read",
        "report:read",
        "customer:read",
        "product:read",
        "quote:read",
    ])
    def test_viewer_allowed(self, permission):
        check_permission(ctx("viewer"), permission)  # should not raise

    @pytest.mark.parametrize("permission", [
        "invoice:create",
        "payment:record",
        "vendor_invoice:approve",
        "product:write",
        "stock:adjust",
        "expense:create",
        "quote:create", "quote:update", "quote:send", "quote:convert",
    ])
    def test_viewer_forbidden(self, permission):
        with pytest.raises(InsufficientPermissionError):
            check_permission(ctx("viewer"), permission)


# ---------------------------------------------------------------------------
# Explicit deny beats role default
# ---------------------------------------------------------------------------

class TestExplicitDeny:

    def test_explicit_deny_overrides_role_permission(self):
        # accountant normally has invoice:read, but explicit deny wins
        c = ctx("accountant", denies={"invoice:read"})
        with pytest.raises(InsufficientPermissionError):
            check_permission(c, "invoice:read")

    def test_explicit_deny_overrides_owner_wildcard(self):
        c = ctx("owner", denies={"product:write"})
        with pytest.raises(InsufficientPermissionError):
            check_permission(c, "product:write")


# ---------------------------------------------------------------------------
# Explicit grant beats role default
# ---------------------------------------------------------------------------

class TestExplicitGrant:

    def test_explicit_grant_allows_beyond_role(self):
        # viewer normally cannot create invoices
        c = ctx("viewer", grants={"invoice:create"})
        check_permission(c, "invoice:create")  # should not raise

    def test_explicit_grant_wildcard(self):
        c = ctx("viewer", grants={"*"})
        check_permission(c, "product:write")  # should not raise
