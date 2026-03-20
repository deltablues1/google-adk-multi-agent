"""
ERP State Machines
==================
Defines allowed document status transitions and computed fields.

Three SEPARATE status concepts — never mix them:
  1. document_status  — lifecycle of the document
  2. payment_status   — computed from amount_paid vs total_gross (not stored in SM)
  3. is_overdue       — computed property, NEVER stored in DB
"""

from decimal import Decimal
from datetime import date
from typing import Optional

from .errors import InvalidStateTransitionError

# ---------------------------------------------------------------------------
# Outgoing invoice document_status transitions
# ---------------------------------------------------------------------------
OUTGOING_INVOICE_DOC_TRANSITIONS: dict[str, list[str]] = {
    "draft":         ["approved", "cancelled"],
    "approved":      ["issued", "cancelled"],
    "issued":        ["fiscalized", "sent", "cancelled"],
    "fiscalized":    ["sent"],           # only B2C after JIR/ZKI received
    "sent":          ["cancelled", "storno_issued"],
    "cancelled":     [],                 # terminal
    "storno_issued": [],                 # terminal — storno document was created
}

# ---------------------------------------------------------------------------
# Vendor invoice (incoming) document_status transitions
# ---------------------------------------------------------------------------
VENDOR_INVOICE_DOC_TRANSITIONS: dict[str, list[str]] = {
    "draft":     ["received", "cancelled"],
    "received":  ["approved", "disputed", "cancelled"],
    "approved":  [],        # payment_status handles paid/partial
    "disputed":  ["received", "cancelled"],
    "cancelled": [],
}


def validate_transition(current: str, target: str, machine: dict) -> None:
    """
    Validate a document_status transition.
    Raises InvalidStateTransitionError if not allowed.
    """
    allowed = machine.get(current, [])
    if target not in allowed:
        raise InvalidStateTransitionError(
            code="INVALID_STATE_TRANSITION",
            message=(
                f"Prijelaz {current!r} → {target!r} nije dozvoljen. "
                f"Dozvoljeni prijelazi: {allowed or ['(nema — terminal stanje)']}"
            ),
        )


def compute_payment_status(amount_paid: Decimal, total_gross: Decimal) -> str:
    """
    Compute payment_status from amounts.
    This is a pure function — the result is denormalized to DB for query performance,
    but never stored via state machine transitions.

    Returns: 'unpaid' | 'partial' | 'paid'
    NEVER allows amount_paid > total_gross (overpayment must be caught before calling).
    """
    if amount_paid <= Decimal("0"):
        return "unpaid"
    if amount_paid >= total_gross:
        return "paid"
    return "partial"


def is_overdue(
    due_date: Optional[date],
    payment_status: str,
    document_status: str,
    as_of: Optional[date] = None,
) -> bool:
    """
    Compute whether an invoice is overdue.
    NEVER stored in DB — always computed on read.

    Rules:
    - due_date must be set
    - payment_status must NOT be 'paid'
    - document_status must NOT be in terminal states
    """
    if due_date is None:
        return False
    if payment_status == "paid":
        return False
    if document_status in ("cancelled", "storno_issued"):
        return False
    check_date = as_of or date.today()
    return due_date < check_date
