"""
State Machine Unit Tests
========================
Pure unit tests — no Firestore, no external services.
Tests OUTGOING_INVOICE_DOC_TRANSITIONS, VENDOR_INVOICE_DOC_TRANSITIONS,
compute_payment_status(), and is_overdue().
"""

import pytest
from decimal import Decimal
from datetime import date

from services.erp.state_machines import (
    OUTGOING_INVOICE_DOC_TRANSITIONS,
    VENDOR_INVOICE_DOC_TRANSITIONS,
    OUTGOING_B2B_DOC_TRANSITIONS,
    QUOTE_DOC_TRANSITIONS,
    validate_transition,
    compute_payment_status,
    compute_fiscalization_deadline,
    is_fiscalization_overdue,
    is_overdue,
)
from services.erp.errors import InvalidStateTransitionError


# ---------------------------------------------------------------------------
# OUTGOING_INVOICE_DOC_TRANSITIONS
# ---------------------------------------------------------------------------

class TestOutgoingInvoiceTransitions:

    @pytest.mark.parametrize("current, target", [
        ("draft",      "approved"),
        ("draft",      "cancelled"),
        ("approved",   "issued"),
        ("approved",   "cancelled"),
        ("issued",     "fiscalized"),
        ("issued",     "sent"),
        ("issued",     "cancelled"),
        ("fiscalized", "sent"),
        ("sent",       "cancelled"),
        ("sent",       "storno_issued"),
    ])
    def test_valid_transitions(self, current, target):
        validate_transition(current, target, OUTGOING_INVOICE_DOC_TRANSITIONS)

    @pytest.mark.parametrize("current, target", [
        ("draft",        "issued"),        # must go through approved first
        ("draft",        "fiscalized"),
        ("approved",     "draft"),         # no reversal
        ("fiscalized",   "cancelled"),     # fiscalized cannot be cancelled directly
        ("cancelled",    "draft"),         # terminal
        ("cancelled",    "approved"),      # terminal
        ("storno_issued","draft"),         # terminal
        ("sent",         "approved"),      # no back-step
    ])
    def test_invalid_transitions_raise(self, current, target):
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(current, target, OUTGOING_INVOICE_DOC_TRANSITIONS)

    def test_terminal_cancelled_has_no_transitions(self):
        assert OUTGOING_INVOICE_DOC_TRANSITIONS["cancelled"] == []

    def test_terminal_storno_issued_has_no_transitions(self):
        assert OUTGOING_INVOICE_DOC_TRANSITIONS["storno_issued"] == []


# ---------------------------------------------------------------------------
# VENDOR_INVOICE_DOC_TRANSITIONS
# ---------------------------------------------------------------------------

class TestVendorInvoiceTransitions:

    @pytest.mark.parametrize("current, target", [
        ("draft",         "received"),
        ("draft",         "cancelled"),
        ("received",      "approved"),
        ("received",      "disputed"),
        ("received",      "cancelled"),
        ("disputed",      "received"),
        ("disputed",      "cancelled"),
        ("approved",      "fisc_reported"),
        ("approved",      "cancelled"),
        ("fisc_reported", "accepted"),
        ("fisc_reported", "rejected"),
    ])
    def test_valid_transitions(self, current, target):
        validate_transition(current, target, VENDOR_INVOICE_DOC_TRANSITIONS)

    @pytest.mark.parametrize("current, target", [
        ("draft",         "approved"),      # must pass through received
        ("approved",      "received"),      # no back-step
        ("fisc_reported", "approved"),      # no back-step
        ("accepted",      "fisc_reported"), # terminal
        ("rejected",      "approved"),      # terminal
        ("cancelled",     "draft"),         # terminal
    ])
    def test_invalid_transitions_raise(self, current, target):
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(current, target, VENDOR_INVOICE_DOC_TRANSITIONS)

    def test_accepted_is_terminal(self):
        assert VENDOR_INVOICE_DOC_TRANSITIONS["accepted"] == []

    def test_rejected_is_terminal(self):
        assert VENDOR_INVOICE_DOC_TRANSITIONS["rejected"] == []

    def test_approved_leads_to_fisc_reported_and_cancelled(self):
        assert set(VENDOR_INVOICE_DOC_TRANSITIONS["approved"]) == {"fisc_reported", "cancelled"}


# ---------------------------------------------------------------------------
# compute_payment_status()
# ---------------------------------------------------------------------------

class TestComputePaymentStatus:

    def test_zero_paid_is_unpaid(self):
        assert compute_payment_status(Decimal("0"), Decimal("100")) == "unpaid"

    def test_negative_paid_is_unpaid(self):
        assert compute_payment_status(Decimal("-1"), Decimal("100")) == "unpaid"

    def test_partial_payment(self):
        assert compute_payment_status(Decimal("50"), Decimal("100")) == "partial"

    def test_full_payment(self):
        assert compute_payment_status(Decimal("100"), Decimal("100")) == "paid"

    def test_overpayment_guard_returns_paid(self):
        # Overpayment must be caught before calling, but function returns paid
        # (not a crash) so callers must validate beforehand
        result = compute_payment_status(Decimal("110"), Decimal("100"))
        assert result == "paid"

    def test_one_cent_partial(self):
        assert compute_payment_status(Decimal("0.01"), Decimal("100")) == "partial"

    def test_one_cent_remaining_is_paid(self):
        assert compute_payment_status(Decimal("99.99"), Decimal("99.99")) == "paid"


# ---------------------------------------------------------------------------
# is_overdue()
# ---------------------------------------------------------------------------

class TestIsOverdue:

    def test_no_due_date_not_overdue(self):
        assert is_overdue(None, "unpaid", "issued") is False

    def test_paid_invoice_not_overdue(self):
        past = date(2020, 1, 1)
        assert is_overdue(past, "paid", "issued") is False

    def test_cancelled_not_overdue(self):
        past = date(2020, 1, 1)
        assert is_overdue(past, "unpaid", "cancelled") is False

    def test_storno_issued_not_overdue(self):
        past = date(2020, 1, 1)
        assert is_overdue(past, "unpaid", "storno_issued") is False

    def test_due_today_not_overdue(self):
        today = date.today()
        # due today means it's not yet past
        assert is_overdue(today, "unpaid", "issued", as_of=today) is False

    def test_due_yesterday_is_overdue(self):
        today = date.today()
        yesterday = date(today.year, today.month, today.day)
        import datetime
        yesterday = today - datetime.timedelta(days=1)
        assert is_overdue(yesterday, "unpaid", "issued", as_of=today) is True

    def test_partial_payment_overdue(self):
        today = date.today()
        import datetime
        past = today - datetime.timedelta(days=30)
        assert is_overdue(past, "partial", "issued", as_of=today) is True

    def test_overdue_90_days(self):
        today = date.today()
        import datetime
        old = today - datetime.timedelta(days=90)
        assert is_overdue(old, "unpaid", "issued", as_of=today) is True


# ---------------------------------------------------------------------------
# QUOTE_DOC_TRANSITIONS
# ---------------------------------------------------------------------------

class TestQuoteDocTransitions:

    @pytest.mark.parametrize("current,target", [
        ("draft", "sent"),
        ("draft", "rejected"),
        ("draft", "expired"),
        ("draft", "cancelled"),
        ("sent", "accepted"),
        ("sent", "rejected"),
        ("sent", "expired"),
        ("sent", "cancelled"),
        ("accepted", "converted"),
    ])
    def test_valid_transitions(self, current, target):
        validate_transition(current, target, QUOTE_DOC_TRANSITIONS)

    @pytest.mark.parametrize("current,target", [
        ("draft", "accepted"),
        ("draft", "converted"),
        ("sent", "draft"),
        ("sent", "converted"),
        ("accepted", "draft"),
        ("accepted", "sent"),
        ("accepted", "rejected"),
        ("rejected", "sent"),
        ("rejected", "accepted"),
        ("expired", "sent"),
        ("converted", "draft"),
        ("cancelled", "draft"),
    ])
    def test_invalid_transitions(self, current, target):
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(current, target, QUOTE_DOC_TRANSITIONS)


# ---------------------------------------------------------------------------
# OUTGOING_B2B_DOC_TRANSITIONS
# ---------------------------------------------------------------------------

class TestOutgoingB2BTransitions:

    @pytest.mark.parametrize("current, target", [
        ("draft",       "approved"),
        ("draft",       "cancelled"),
        ("approved",    "issued"),
        ("approved",    "cancelled"),
        ("issued",      "eracun_sent"),
        ("issued",      "cancelled"),
        ("eracun_sent", "delivered"),
        ("eracun_sent", "rejected"),
        ("eracun_sent", "cancelled"),
        ("delivered",   "accepted"),
        ("delivered",   "storno_issued"),
        ("accepted",    "storno_issued"),
        ("rejected",    "issued"),
    ])
    def test_valid_transitions(self, current, target):
        validate_transition(current, target, OUTGOING_B2B_DOC_TRANSITIONS)

    @pytest.mark.parametrize("current, target", [
        ("draft",       "issued"),          # must go through approved
        ("approved",    "eracun_sent"),     # must go through issued
        ("eracun_sent", "approved"),        # no back-step
        ("accepted",    "delivered"),       # no back-step
        ("cancelled",   "draft"),           # terminal
        ("storno_issued", "draft"),         # terminal
    ])
    def test_invalid_transitions_raise(self, current, target):
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(current, target, OUTGOING_B2B_DOC_TRANSITIONS)

    def test_no_fiscalization_step(self):
        # B2B has no 'fiscalized' state — that's B2C only
        assert "fiscalized" not in OUTGOING_B2B_DOC_TRANSITIONS


# ---------------------------------------------------------------------------
# compute_fiscalization_deadline() and is_fiscalization_overdue()
# ---------------------------------------------------------------------------

class TestFiscalizationDeadline:
    import datetime as _dt

    def test_five_weekdays_from_monday(self):
        # Monday 2026-01-05 + 5 business days = Monday 2026-01-12
        from datetime import date
        d = compute_fiscalization_deadline(date(2026, 1, 5))
        assert d == date(2026, 1, 12)

    def test_five_weekdays_crosses_weekend(self):
        # Wednesday 2026-01-07 + 5 business days = Wednesday 2026-01-14
        from datetime import date
        d = compute_fiscalization_deadline(date(2026, 1, 7))
        assert d == date(2026, 1, 14)

    def test_friday_crosses_two_weekend_days(self):
        # Friday 2026-01-09 + 5 business days = Friday 2026-01-16
        from datetime import date
        d = compute_fiscalization_deadline(date(2026, 1, 9))
        assert d == date(2026, 1, 16)

    def test_not_overdue_on_deadline_day(self):
        from datetime import date
        received = date(2026, 1, 5)  # Monday
        deadline = compute_fiscalization_deadline(received)  # 2026-01-12
        assert is_fiscalization_overdue(received, "approved", as_of=deadline) is False

    def test_overdue_day_after_deadline(self):
        from datetime import date, timedelta
        received = date(2026, 1, 5)
        deadline = compute_fiscalization_deadline(received)
        assert is_fiscalization_overdue(received, "approved", as_of=deadline + timedelta(days=1)) is True

    def test_not_overdue_if_already_fisc_reported(self):
        from datetime import date, timedelta
        received = date(2020, 1, 1)
        assert is_fiscalization_overdue(received, "fisc_reported") is False

    def test_not_overdue_if_accepted(self):
        from datetime import date
        assert is_fiscalization_overdue(date(2020, 1, 1), "accepted") is False

    def test_not_overdue_if_rejected(self):
        from datetime import date
        assert is_fiscalization_overdue(date(2020, 1, 1), "rejected") is False

    def test_not_overdue_if_cancelled(self):
        from datetime import date
        assert is_fiscalization_overdue(date(2020, 1, 1), "cancelled") is False

    def test_no_received_date_never_overdue(self):
        assert is_fiscalization_overdue(None, "approved") is False
