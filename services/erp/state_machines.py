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
#
# Extended for eRačun compliance (NN 89/2025):
#   - fisc_reported: inbound fiscalization reported to Porezna Uprava
#   - accepted/rejected: buyer acceptance status (mandatory for eRačun)
#   - Fiscalization of received invoice must happen within 5 business days
# ---------------------------------------------------------------------------
VENDOR_INVOICE_DOC_TRANSITIONS: dict[str, list[str]] = {
    "draft":          ["received", "cancelled"],
    "received":       ["approved", "disputed", "cancelled"],
    "approved":       ["fisc_reported", "cancelled"],
    "fisc_reported":  ["accepted", "rejected"],       # after fiscal reporting to Porezna
    "accepted":       [],                              # terminal for document flow; payment tracked separately
    "rejected":       [],                              # terminal — rejection_reason required
    "disputed":       ["received", "cancelled"],
    "cancelled":      [],
}

# ---------------------------------------------------------------------------
# Outgoing B2B/B2G invoice document_status transitions
#
# Different from B2C: no JIR/ZKI fiscalization step.
# Instead: UBL generation → signing → delivery via AP/email → acknowledgement.
# ---------------------------------------------------------------------------
OUTGOING_B2B_DOC_TRANSITIONS: dict[str, list[str]] = {
    "draft":         ["approved", "cancelled"],
    "approved":      ["issued", "cancelled"],
    "issued":        ["eracun_sent", "cancelled"],     # UBL generated + signed
    "eracun_sent":   ["delivered", "rejected", "cancelled"],  # sent to AP/email
    "delivered":     ["accepted", "storno_issued"],
    "accepted":      ["storno_issued"],                # buyer confirmed receipt
    "rejected":      ["issued"],                       # buyer rejected → can re-issue
    "cancelled":     [],
    "storno_issued": [],
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


# ---------------------------------------------------------------------------
# Quote document_status transitions
# ---------------------------------------------------------------------------
QUOTE_DOC_TRANSITIONS: dict[str, list[str]] = {
    "draft":     ["sent", "rejected", "expired", "cancelled"],
    "sent":      ["accepted", "rejected", "expired", "cancelled"],
    "accepted":  ["converted"],
    "rejected":  [],      # terminal
    "expired":   [],      # terminal
    "converted": [],      # terminal
    "cancelled": [],      # terminal
}


def get_outgoing_machine(invoice_type: str) -> dict:
    """
    Return the correct state machine for an outgoing invoice type.

    B2C uses the original machine (with JIR/ZKI fiscalization step).
    B2B/B2G/EU/INT use the eRačun machine (UBL → delivery → acknowledgement).
    """
    if invoice_type == "b2c":
        return OUTGOING_INVOICE_DOC_TRANSITIONS
    return OUTGOING_B2B_DOC_TRANSITIONS


def compute_fiscalization_deadline(received_date: date) -> date:
    """
    Compute the deadline for fiscalizing a received vendor invoice.
    Per NN 89/2025: 5 business days from received_date.

    Counts only weekdays (Mon-Fri). Does not account for Croatian public holidays.
    """
    deadline = received_date
    business_days = 0
    while business_days < 5:
        deadline = deadline + __import__('datetime').timedelta(days=1)
        if deadline.weekday() < 5:  # Mon=0 .. Fri=4
            business_days += 1
    return deadline


def is_fiscalization_overdue(
    received_date: Optional[date],
    document_status: str,
    as_of: Optional[date] = None,
) -> bool:
    """
    Check if a vendor invoice has exceeded its 5-business-day fiscalization deadline.
    Only applies to approved invoices that haven't been fiscally reported yet.
    """
    if received_date is None:
        return False
    if document_status in ("fisc_reported", "accepted", "rejected", "cancelled"):
        return False
    check_date = as_of or date.today()
    deadline = compute_fiscalization_deadline(received_date)
    return check_date > deadline


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
