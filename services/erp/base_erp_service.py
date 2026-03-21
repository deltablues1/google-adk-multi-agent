"""
Base ERP Service
================
Shared utilities: Firestore client, display ID generation, permission checks, audit log.
All ERP services inherit from BaseERPService.
"""

import os
import logging
from decimal import Decimal
from datetime import datetime, timezone, date
from typing import Optional, Any
from uuid import uuid4

from google.cloud.firestore_v1.async_client import AsyncClient
from google.cloud.firestore_v1 import Increment

from .errors import InsufficientPermissionError
from .request_context import ERPRequestContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Permission model
# ---------------------------------------------------------------------------
ROLE_PERMISSIONS: dict[str, set] = {
    "owner":       {"*"},
    "accountant":  {
        "invoice:read", "invoice:create",
        "payment:record",
        "vendor_invoice:read", "vendor_invoice:approve",
        "customer:read", "customer:create", "customer:update",
        "product:read", "product:write", "stock:adjust",
        "report:read",
        "expense:read",
        "quote:read", "quote:create", "quote:update", "quote:send", "quote:convert",
    },
    "employee":    {
        "invoice:read",
        "vendor_invoice:read", "vendor_invoice:create",
        "expense:create",
        "customer:read",
        "product:read", "stock:adjust",
        "quote:read", "quote:create", "quote:update", "quote:send",
    },
    "viewer":      {
        "invoice:read",
        "vendor_invoice:read",
        "report:read",
        "customer:read",
        "product:read",
        "quote:read",
    },
}


def check_permission(ctx: ERPRequestContext, permission: str) -> None:
    """
    Enforce permission check.

    Precedence (first match wins):
      1. explicit deny  → InsufficientPermissionError (403)
      2. explicit grant → allow
      3. role wildcard '*' → allow
      4. role permission list → allow if found
      5. default → InsufficientPermissionError (403)
    """
    if permission in ctx.denies:
        raise InsufficientPermissionError(
            code="INSUFFICIENT_PERMISSION",
            message=f"Permission '{permission}' je eksplicitno zabranjena za ovog korisnika.",
        )
    if permission in ctx.grants or "*" in ctx.grants:
        return
    role_perms = ROLE_PERMISSIONS.get(ctx.role, set())
    if "*" in role_perms or permission in role_perms:
        return
    raise InsufficientPermissionError(
        code="INSUFFICIENT_PERMISSION",
        message=f"Uloga '{ctx.role}' nema permission '{permission}'.",
    )


# ---------------------------------------------------------------------------
# Firestore helpers
# ---------------------------------------------------------------------------
_DEFAULT_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "fabled-sector-476018-n3")

_db_instance: Optional[AsyncClient] = None


def get_firestore_db(project_id: Optional[str] = None) -> AsyncClient:
    """Lazy singleton Firestore async client."""
    global _db_instance
    if _db_instance is None:
        proj = project_id or _DEFAULT_PROJECT
        _db_instance = AsyncClient(project=proj)
        logger.info(f"[ERP] Firestore client initialized (project={proj})")
    return _db_instance


# ---------------------------------------------------------------------------
# Display ID generation
# ---------------------------------------------------------------------------
async def generate_display_id(company_id: str, prefix: str, db: AsyncClient) -> str:
    """
    Generate a sequential human-readable display ID.
    Format: {PREFIX}-{YEAR}-{COUNTER:06d}  e.g. PAY-2026-000042

    Uses Firestore atomic increment — safe for concurrent requests.
    Internal doc IDs are always UUID; this is only for human display.
    """
    year = datetime.now(timezone.utc).year
    counter_key = f"{company_id}-{prefix}-{year}"
    counter_ref = db.collection("erp_counters").document(counter_key)

    # Atomic increment
    await counter_ref.set({"counter": Increment(1)}, merge=True)
    snap = await counter_ref.get()
    counter_val = snap.to_dict().get("counter", 1)

    return f"{prefix}-{year}-{counter_val:06d}"


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------
def serialize_doc(data: dict) -> dict:
    """Convert Firestore-specific types to JSON-serializable equivalents."""
    result = {}
    for k, v in data.items():
        if hasattr(v, "isoformat"):        # datetime / date
            result[k] = v.isoformat()
        elif isinstance(v, Decimal):
            result[k] = float(v)
        elif isinstance(v, dict):
            result[k] = serialize_doc(v)
        elif isinstance(v, list):
            result[k] = [
                serialize_doc(i) if isinstance(i, dict) else
                (i.isoformat() if hasattr(i, "isoformat") else
                 float(i) if isinstance(i, Decimal) else i)
                for i in v
            ]
        else:
            result[k] = v
    return result


# ---------------------------------------------------------------------------
# Audit log helper
# ---------------------------------------------------------------------------
async def write_audit(
    action: str,
    entity_type: str,
    entity_id: str,
    display_id: Optional[str],
    ctx: ERPRequestContext,
    data: Optional[dict] = None,
    db: Optional[AsyncClient] = None,
) -> None:
    """
    Write an immutable audit entry to the audit_log collection.
    Silently swallows errors — audit failure must not block business operations.
    """
    try:
        _db = db or get_firestore_db()
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": ctx.user_id,
            "company_id": ctx.company_id,
            "request_id": ctx.request_id,
            "agent_name": "erp_service",
            "action_type": action,
            "action_description": f"{action} {entity_type} {display_id or entity_id}",
            "target_resource": entity_id,
            "target_service": "erp",
            "display_id": display_id,
            "entity_type": entity_type,
            "status": "success",
            "metadata": serialize_doc(data) if data else {},
        }
        await _db.collection("audit_log").document(str(uuid4())).set(entry)
    except Exception as exc:
        logger.warning(f"[ERP Audit] Failed to write audit log: {exc}")


# ---------------------------------------------------------------------------
# Soft-delete helper
# ---------------------------------------------------------------------------
async def soft_delete_doc(
    collection: str,
    doc_id: str,
    ctx: ERPRequestContext,
    db: Optional[AsyncClient] = None,
) -> None:
    """Mark a document as soft-deleted. Never physically removes data."""
    _db = db or get_firestore_db()
    await _db.collection(collection).document(doc_id).update({
        "deleted": True,
        "deleted_at": datetime.now(timezone.utc).isoformat(),
        "deleted_by": ctx.user_id,
    })


# ---------------------------------------------------------------------------
# Base service class
# ---------------------------------------------------------------------------
class BaseERPService:
    """Base class for all ERP services. Provides shared Firestore client."""

    def __init__(self, project_id: Optional[str] = None):
        self._project_id = project_id or _DEFAULT_PROJECT

    def _get_db(self) -> AsyncClient:
        return get_firestore_db(self._project_id)
