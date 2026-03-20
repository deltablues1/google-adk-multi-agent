"""
ERP Test Fixtures
==================
Shared fixtures for ERP tests.

Isolation strategy:
- Unit tests (state_machines, permissions): no Firestore, no fixtures needed
- Integration/API tests: use a unique company_id per test run to avoid
  contaminating production data. Ideally use Firestore emulator or a
  separate test GCP project for full isolation.
"""

import asyncio
import pytest
from uuid import uuid4
from decimal import Decimal

from services.erp.request_context import ERPRequestContext


@pytest.fixture(scope="session")
def event_loop():
    """
    Session-scoped event loop for integration tests.
    Prevents "Event loop is closed" errors when Firestore/gRPC connections
    are reused across multiple async tests and test modules.
    The Firestore async client + gRPC channel must run on the same loop
    for the entire test session.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def make_ctx(
    role: str = "owner",
    user_id: str = "test-user",
    company_id: str = None,
    grants: set = None,
    denies: set = None,
) -> ERPRequestContext:
    """Build an ERPRequestContext for testing."""
    return ERPRequestContext(
        user_id=user_id,
        company_id=company_id or "test-company",
        role=role,
        grants=grants or set(),
        denies=denies or set(),
        request_id=str(uuid4()),
    )


@pytest.fixture
def owner_ctx():
    return make_ctx(role="owner")


@pytest.fixture
def accountant_ctx():
    return make_ctx(role="accountant")


@pytest.fixture
def employee_ctx():
    return make_ctx(role="employee")


@pytest.fixture
def viewer_ctx():
    return make_ctx(role="viewer")


@pytest.fixture
def isolated_company_id():
    """Unique company_id per test run — prevents cross-test contamination in Firestore."""
    return f"test_{uuid4().hex}"
