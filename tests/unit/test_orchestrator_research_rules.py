"""
Two things the orchestrator prompt had no rule for.

First, it forwarded the raw transcript to the researcher, which starts every
run with no memory: measured 2026-09-03, a price question arrived as the voice
persona plus "Korisnik je rekao: ...", with no country, currency or purpose, and
came back shallow. Rule 9 makes it write a brief.

Second, a research report is delivered to a channel that reads it out loud.
Rule 10 routes those through scribe and speaks three sentences plus a link. It
keys on the [VOICE_ASSISTANT_PROFILE] marker, so that marker is pinned here —
renaming it in config/voice_persona.py would silently disable the rule.

Run with:
    pytest tests/unit/test_orchestrator_research_rules.py -v
"""

from pathlib import Path

import pytest

from config.voice_persona import build_voice_persona_preamble, wrap_agent_voice_message

PROMPT = (
    Path(__file__).resolve().parents[2] / "agents" / "orchestrator" / "instructions.md"
).read_text(encoding="utf-8")

VOICE_MARKER = "[VOICE_ASSISTANT_PROFILE]"


def _rule(number: str, until: str) -> str:
    return PROMPT.split(f"### Rule {number}:")[1].split(until)[0]


class TestRule9BriefsTheResearcher:
    def test_exists(self):
        assert "### Rule 9: Brief the researcher" in PROMPT

    @pytest.mark.parametrize("element", ["Depth", "DEEP", "Hrvatska", "EUR", "What to skip"])
    def test_names_the_parts_of_a_brief(self, element):
        assert element in _rule("9", "### Rule 10")

    def test_shows_the_wrong_shape_too(self):
        rule = _rule("9", "### Rule 10")
        assert "Korisnik je rekao:" in rule, "the failing example is the useful half"


class TestRule10RoutesVoiceResearchToADocument:
    def test_exists(self):
        assert "### Rule 10:" in PROMPT

    def test_chains_researcher_into_scribe(self):
        rule = _rule("10", "## Agent Routing Guide")
        assert "researcher" in rule and "scribe" in rule
        assert "three sentences" in rule.lower()


class TestVoiceMarkerContract:
    """Rule 10 fires on a marker the interface actually sends."""

    def test_marker_is_in_the_prompt(self):
        assert VOICE_MARKER in PROMPT

    def test_persona_preamble_still_emits_it(self):
        assert VOICE_MARKER in build_voice_persona_preamble()

    def test_orchestrator_receives_it_on_the_voice_path(self):
        # This is exactly what base_interface hands the orchestrator for voice.
        assert VOICE_MARKER in wrap_agent_voice_message("istraži cijene dizalica")


class TestRule10DoesNotLeakOntoTextChannels:
    """Reaching for scribe on a typed question discarded a finished 13-minute run."""

    def test_it_says_only_on_the_voice_channel(self):
        rule = _rule("10", "## Agent Routing Guide")
        assert "only" in rule.lower()
        assert "text channel" in rule.lower()

    def test_it_names_the_request_argument(self):
        rule = _rule("10", "## Agent Routing Guide")
        assert "request=" in rule, "an argument-less worker call crashes the run"
