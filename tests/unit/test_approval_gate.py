"""
The tools that reach outside the house now need a real yes, not a promise.

Before this, exactly three MQTT switches and proposed meeting slots were gated
in code. Sending mail, sharing a document with "anyone", moving stock and
deleting a calendar entry were defended by a sentence in a prompt — the same
defence that fails when the model decides the user already agreed, and the one
a prompt injection inside a fetched page argues with directly.

Run with:
    pytest tests/unit/test_approval_gate.py -v
"""

import pytest

from services import approvals
from services.approval_gate import approval_before_tool


class _Tool:
    def __init__(self, name):
        self.name = name


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    approvals.reset()
    approvals.set_session("s1")
    monkeypatch.setenv("APPROVAL_TRUSTED_EMAIL_DOMAINS", "lux-tech.hr")
    yield
    approvals.reset()


def _call(tool_name, **args):
    return approval_before_tool(tool=_Tool(tool_name), args=args)


class TestUngatedToolsAreUntouched:
    def test_a_read_only_tool_passes_straight_through(self):
        assert _call("erp_find_product", query="cijev") is None

    def test_reading_mail_is_not_gated(self):
        assert _call("gmail_list_messages", query="is:unread") is None


class TestConsequentialWritesAreHeld:
    @pytest.mark.parametrize(
        "name,args",
        [
            ("erp_adjust_stock", {"product_id": "P1", "quantity_delta": -5}),
            ("erp_create_product", {"name": "Cijev 20mm"}),
            ("erp_record_payment", {"invoice_id": "I1", "amount": 500}),
            ("calendar_delete_event", {"event_id": "E1"}),
        ],
    )
    def test_first_call_asks(self, name, args):
        result = _call(name, **args)
        assert result["status"] == "needs_confirmation"
        assert result["action"] == name

    def test_the_same_call_still_fails_without_a_user_turn(self):
        """The model cannot confirm on its own behalf by calling twice."""
        _call("erp_adjust_stock", product_id="P1", quantity_delta=-5)
        again = _call("erp_adjust_stock", product_id="P1", quantity_delta=-5)
        assert again["status"] == "needs_confirmation"

    def test_it_goes_through_after_the_user_says_yes(self):
        _call("erp_adjust_stock", product_id="P1", quantity_delta=-5)
        approvals.on_user_turn("s1", affirmative=True)
        assert _call("erp_adjust_stock", product_id="P1", quantity_delta=-5) is None

    def test_an_echoed_yes_does_not_write_twice(self):
        _call("erp_adjust_stock", product_id="P1", quantity_delta=-5)
        approvals.on_user_turn("s1", affirmative=True)
        assert _call("erp_adjust_stock", product_id="P1", quantity_delta=-5) is None
        assert _call("erp_adjust_stock", product_id="P1", quantity_delta=-5) is not None

    def test_changing_the_amount_needs_a_new_confirmation(self):
        """Confirming 5 must not authorise 50."""
        _call("erp_adjust_stock", product_id="P1", quantity_delta=-5)
        approvals.on_user_turn("s1", affirmative=True)
        assert _call("erp_adjust_stock", product_id="P1", quantity_delta=-50) is not None


class TestGmailIsGatedByRecipient:
    def test_a_colleague_on_a_trusted_domain_goes_through(self):
        assert _call("gmail_send_message", to="ivan@lux-tech.hr", subject="Ponuda") is None

    def test_an_outside_address_is_held(self):
        held = _call("gmail_send_message", to="stranac@example.com", subject="Ponuda")
        assert held["status"] == "needs_confirmation"
        assert "stranac@example.com" in held["question"]

    def test_one_outside_address_among_trusted_ones_is_enough(self):
        held = _call(
            "gmail_send_message",
            to="ivan@lux-tech.hr",
            cc="stranac@example.com",
            subject="Ponuda",
        )
        assert held is not None

    def test_with_no_trusted_domains_declared_every_send_is_held(self, monkeypatch):
        monkeypatch.delenv("APPROVAL_TRUSTED_EMAIL_DOMAINS", raising=False)
        assert _call("gmail_send_message", to="ivan@lux-tech.hr", subject="x") is not None


class TestDriveIsGatedOnlyForPublishing:
    def test_sharing_with_a_person_is_ordinary_work(self):
        assert _call("drive_share_file", file_id="F1", email="ivan@lux-tech.hr", type="user") is None

    def test_anyone_with_the_link_is_held(self):
        held = _call("drive_share_file", file_id="F1", type="anyone", role="reader")
        assert held["status"] == "needs_confirmation"


class TestFailureModes:
    def test_a_broken_rule_does_not_block_the_house(self, monkeypatch):
        from services import approval_gate

        monkeypatch.setitem(
            approval_gate.RULES,
            "erp_adjust_stock",
            approval_gate._Rule(
                when=lambda a: (_ for _ in ()).throw(RuntimeError("boom")),
                key=lambda a: {},
                question=lambda a: "",
            ),
        )
        assert _call("erp_adjust_stock", product_id="P1", quantity_delta=-5) is None

    def test_the_gate_can_be_switched_off(self, monkeypatch):
        monkeypatch.setenv("APPROVAL_GATE_ENABLED", "false")
        assert _call("erp_adjust_stock", product_id="P1", quantity_delta=-5) is None


class TestTheReplyGoesBackToTheRightAgent:
    def test_a_stock_question_pins_the_warehouse_lane(self):
        _call("erp_adjust_stock", product_id="P1", quantity_delta=-5)
        assert approvals.pending_lane("s1") == "skladistar"

    def test_a_mail_question_pins_the_mailer_lane(self):
        _call("gmail_send_message", to="stranac@example.com", subject="x")
        assert approvals.pending_lane("s1") == "mailer"


class TestAutonomousRuns:
    """The scheduler fires at 07:30 with nobody to ask."""

    def test_a_gated_action_is_refused_not_held(self):
        approvals.set_autonomous(True)
        result = _call("gmail_send_message", to="stranac@example.com", subject="Izvještaj")

        assert result["status"] == "not_permitted"
        assert result["error"] == "AUTONOMOUS_RUN_NEEDS_CONFIRMATION"

    def test_nothing_is_left_pending_for_a_later_yes_to_arm(self):
        """Registering here is the dangerous part: a 'da' typed in Telegram
        hours later must not authorise a job's held mail."""
        approvals.set_autonomous(True)
        _call("gmail_send_message", to="stranac@example.com", subject="Izvještaj")

        assert approvals.has_pending("s1") is False
        assert approvals.has_pending("global") is False

    def test_the_model_is_told_to_stop_rather_than_retry(self):
        approvals.set_autonomous(True)
        result = _call("erp_adjust_stock", product_id="P1", quantity_delta=-5)
        assert "Nemoj ponavljati poziv" in result["message"]

    def test_ungated_work_still_runs_autonomously(self):
        approvals.set_autonomous(True)
        assert _call("erp_find_product", query="cijev") is None
        assert _call("gmail_send_message", to="ivan@lux-tech.hr", subject="x") is None

    def test_interactive_runs_are_unaffected(self):
        approvals.set_autonomous(False)
        held = _call("erp_adjust_stock", product_id="P1", quantity_delta=-5)
        assert held["status"] == "needs_confirmation"
