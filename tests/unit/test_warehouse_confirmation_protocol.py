"""
The warehouse agent must not wait for a turn it will never get.

Its prompt required the user to confirm "u SLJEDEĆOJ poruci" before any write.
That works on the direct voice lane, where skladistar holds its own multi-turn
conversation. As an orchestrator sub-agent it is created fresh for every call
and has no next message — so on 2026-09-04 it asked for confirmation five times
in a row and never wrote anything, while the code gate sat armed and ready.

The confirmation now lives in code, so the prompt tells it to call the tool and
relay whatever the gate says back.

Run with:
    pytest tests/unit/test_warehouse_confirmation_protocol.py -v
"""

from pathlib import Path

import pytest

AGENTS = Path(__file__).resolve().parents[2] / "agents"
SKLADISTAR = (AGENTS / "skladistar" / "instructions.md").read_text(encoding="utf-8")
ORCHESTRATOR = (AGENTS / "orchestrator" / "instructions.md").read_text(encoding="utf-8")


class TestWarehouseCallsTheToolInsteadOfWaiting:
    def test_it_no_longer_waits_for_a_next_message(self):
        assert "NE čekaj potvrdu prije nego pozoveš alat" in SKLADISTAR

    def test_it_knows_the_gate_is_in_code(self):
        assert "provodi je sustav" in SKLADISTAR

    def test_it_relays_needs_confirmation_and_stops(self):
        assert "needs_confirmation" in SKLADISTAR

    def test_it_must_repeat_identical_arguments(self):
        assert "identičnim argumentima" in SKLADISTAR

    def test_confirming_five_does_not_authorise_fifty(self):
        assert "pedeset" in SKLADISTAR

    def test_a_refusal_still_stops_it(self):
        for word in ("odustani", "stani", "nemoj"):
            assert word in SKLADISTAR


class TestOrchestratorRelaysTheWholeRequest:
    def _rule(self):
        return ORCHESTRATOR.split("### Rule 9c:")[1].split("### Rule 10")[0]

    def test_the_rule_exists(self):
        assert "### Rule 9c:" in ORCHESTRATOR

    def test_it_forbids_forwarding_a_bare_yes(self):
        rule = self._rule()
        assert 'request="da"' in rule
        assert "WRONG" in rule

    def test_it_shows_the_full_repeat(self):
        rule = self._rule()
        assert "RIGHT" in rule
        assert "Korisnik je potvrdio" in rule

    def test_it_says_values_must_not_change(self):
        assert "identical" in self._rule().lower()


class TestOrchestratorDoesNotPreEmptTheGate:
    """Asking before attempting leaves nothing for the user's "da" to arm, so
    the write stays a full turn away — seen on a stock removal, 2026-09-04."""

    def _rule(self):
        return ORCHESTRATOR.split("### Rule 9c:")[1].split("### Rule 10")[0]

    def test_it_forbids_asking_on_the_workers_behalf(self):
        assert "Do not ask for permission on the worker's behalf" in self._rule()

    def test_it_explains_what_asking_first_costs(self):
        rule = self._rule()
        assert "nothing waiting" in rule
        assert "one full turn away" in rule


class TestOrchestratorDoesNotCallTheGateAFault:
    """A deletion working exactly as designed was reported as "naišao sam na
    problem, sustav traži potvrdu u krug" — which teaches the user to distrust
    the mechanism protecting them."""

    def _rule(self):
        return ORCHESTRATOR.split("### Rule 9c:")[1].split("### Rule 10")[0]

    def test_it_says_a_confirmation_request_is_not_a_malfunction(self):
        assert "not a malfunction" in self._rule()

    def test_it_forbids_calling_it_an_error_or_a_loop(self):
        rule = self._rule()
        assert "loop" in rule and "error" in rule

    def test_it_says_retrying_in_the_same_turn_cannot_help(self):
        assert "cannot help" in self._rule()
