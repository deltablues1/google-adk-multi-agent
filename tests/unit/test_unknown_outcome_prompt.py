"""A lost answer is not a failure, and the prompts have to say so.

tools/resilience/retry_handler.py deliberately removed the automatic retry from
non-idempotent writes: repeating a send or a create after a timeout duplicates
it, because the write may already have landed and only the response was lost.
Those tools now surface status/outcome "unknown" instead of "failed".

The mailer's prompt still said "Send failure: report error with details, suggest
retry" - reintroducing, one level up, exactly the duplicate the missing retry
was there to prevent. These tests pin the replacement, and tie the agent list to
the modules that can actually produce an unknown outcome.

Run with:
    pytest tests/unit/test_unknown_outcome_prompt.py -v
"""

import re
from pathlib import Path

import pytest

from agents.adk_agents.adk_agent_factory import (
    _UNKNOWN_OUTCOME_AGENTS,
    _append_unknown_outcome_rule,
    load_instruction_file,
    load_shared_fragment,
)
from config.runtime_patches import CACHE_BREAK

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools" / "adk_tools"

# Which agent owns each tool module. Only modules that can return an unknown
# outcome need an entry; the test below fails if a new one appears.
MODULE_OWNER = {
    "contacts_adk_tools": "rolodex",
    "docs_adk_tools": "scribe",
    "drive_adk_tools": "librarian",
    "gmail_adk_tools": "mailer",
    "sheets_adk_tools": "analyst",
    "tasks_adk_tools": "tracker",
    "_offload": None,  # infrastructure, not an agent's tool surface
    "calendar_adk_tools": "secretary",
    "mqtt_adk_tools": "smart_home",
}

PROMPT_DIR = {"smart_orchestrator": "orchestrator"}


def _modules_returning_unknown():
    found = set()
    for path in TOOLS_DIR.glob("*.py"):
        src = path.read_text(encoding="utf-8")
        if re.search(r'"outcome"\]?\s*[:=]\s*"unknown"', src) or "UnconfirmedWrite" in src:
            found.add(path.stem)
    return found


class TestSharedFragment:
    def test_it_exists(self):
        assert load_shared_fragment("unknown_outcome")

    def test_it_forbids_the_repeat_and_names_the_check(self):
        fragment = load_shared_fragment("unknown_outcome")
        assert "NE ponavljaj isti poziv" in fragment
        assert "gmail_search_threads" in fragment
        assert "unknown" in fragment

    def test_an_empty_search_result_is_not_proof_of_non_execution(self):
        """The hole the first version left: 'not found' authorised a retry."""
        fragment = load_shared_fragment("unknown_outcome")
        assert "nije \"nije se dogodilo\"" in fragment
        assert "NE ovlašćuje ponovni pokušaj" in fragment

    def test_a_match_must_identify_this_action_not_the_topic(self):
        """An older mail with the same subject is not evidence."""
        fragment = load_shared_fragment("unknown_outcome")
        assert "poklapa s tvojom radnjom" in fragment
        assert "POSLIJE" in fragment

    def test_the_retry_belongs_to_the_user(self):
        fragment = load_shared_fragment("unknown_outcome")
        assert "njegova odluka, ne tvoja pretpostavka" in fragment

    @pytest.mark.parametrize("name", sorted(_UNKNOWN_OUTCOME_AGENTS))
    def test_every_listed_agent_receives_it(self, name):
        built = _append_unknown_outcome_rule(
            name, load_instruction_file(PROMPT_DIR.get(name, name))
        )
        assert "ne zna je li uspio" in built

    @pytest.mark.parametrize("name", sorted(_UNKNOWN_OUTCOME_AGENTS))
    def test_it_stays_on_the_cached_side(self, name):
        built = _append_unknown_outcome_rule(
            name, load_instruction_file(PROMPT_DIR.get(name, name))
        )
        static, _, volatile = built.partition(CACHE_BREAK)
        assert "ne zna je li uspio" in static
        assert "ne zna je li uspio" not in volatile


class TestEveryUnknownProducingModuleHasAnInformedOwner:
    """A new unknown-returning tool must not land on an uninformed agent."""

    @pytest.mark.parametrize("module", sorted(_modules_returning_unknown()))
    def test_owner_is_known_and_told(self, module):
        assert module in MODULE_OWNER, (
            f"{module} can return an unknown outcome but no agent is recorded "
            "as owning it"
        )
        owner = MODULE_OWNER[module]
        if owner is None:
            return
        prompt = load_instruction_file(owner) or ""
        informed = owner in _UNKNOWN_OUTCOME_AGENTS or "unknown" in prompt
        assert informed, (
            f"{owner} owns {module}, which can report an unknown outcome, but "
            "its prompt never learns what that means"
        )


class TestMailerNoLongerSuggestsRetryingASend:
    def test_the_old_line_is_gone(self):
        prompt = load_instruction_file("mailer")
        assert "Send failure: report error with details, suggest retry" not in prompt

    def test_it_distinguishes_proven_from_unproven(self):
        prompt = load_instruction_file("mailer")
        errors = prompt.split("## Error Handling")[1]
        assert "Proven" in errors and "Unproven" in errors
        assert "Do NOT re-send" in errors

    def test_the_sent_check_is_bound_to_this_message(self):
        prompt = load_instruction_file("mailer")
        errors = prompt.split("## Error Handling")[1]
        assert "send time after your attempt" in errors
        assert "including" in errors and "an empty result" in errors
