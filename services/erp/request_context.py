"""
ERP Request Context
===================
Explicit tenant + user context passed to all service methods.
No "magic" — context is always built from a known source (FastAPI dependency or session state).
"""

from dataclasses import dataclass, field
from uuid import uuid4
from typing import Optional


@dataclass
class ERPRequestContext:
    """
    Carries authenticated user + company information through the ERP service stack.

    Fields:
        user_id     — authenticated user identifier
        company_id  — tenant isolation key (every Firestore query filters by this)
        role        — base role for permission defaults
        grants      — explicit permission grants (override role defaults)
        denies      — explicit permission denies (beat everything, including grants)
        request_id  — unique per-request ID for tracing and audit correlation
    """
    user_id: str
    company_id: str
    role: str
    grants: list = field(default_factory=list)
    denies: list = field(default_factory=list)
    request_id: str = field(default_factory=lambda: str(uuid4()))


def build_context(user_doc: dict) -> ERPRequestContext:
    """
    Build ERPRequestContext from a Firestore erp_users document dict.

    Expected user_doc keys:
        user_id, company_id, role, permissions: {grants: [], denies: []}
    """
    permissions = user_doc.get("permissions", {})
    return ERPRequestContext(
        user_id=user_doc["user_id"],
        company_id=user_doc["company_id"],
        role=user_doc.get("role", "viewer"),
        grants=permissions.get("grants", []),
        denies=permissions.get("denies", []),
    )


def build_system_context(company_id: str) -> ERPRequestContext:
    """
    Build a system-level context for scheduled jobs and internal operations.
    Has owner-level permissions.
    """
    return ERPRequestContext(
        user_id="system",
        company_id=company_id,
        role="owner",
        grants=["*"],
        denies=[],
    )
