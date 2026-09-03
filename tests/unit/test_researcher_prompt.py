"""
The researcher's prompt must describe the tools it actually has.

Every drift here cost real research quality: the tool table promised
google_search_simple returned raw URLs while the code returned an AI summary,
and Rule 5 told the model to expect a FIRECRAWL_API_KEY error from a scraper
that tries Jina first. A model cannot plan around tools that are described
wrongly, so these are pinned.

Run with:
    pytest tests/unit/test_researcher_prompt.py -v
"""

from pathlib import Path

import pytest

PROMPT = (
    Path(__file__).resolve().parents[2] / "agents" / "researcher" / "instructions.md"
).read_text(encoding="utf-8")


class TestToolDescriptionsMatchImplementation:
    def test_simple_search_is_not_sold_as_an_ai_summary(self):
        row = next(l for l in PROMPT.splitlines() if l.startswith("| google_search_simple"))
        assert "Custom Search" in row
        assert "snippet" in row.lower()

    def test_advanced_scraper_names_jina_first(self):
        row = next(l for l in PROMPT.splitlines() if l.startswith("| scrape_url_advanced"))
        assert "Jina" in row
        assert "Jina" in PROMPT.split("### Rule 5")[1].split("### Rule 6")[0]


class TestPriceMode:
    def test_exists(self):
        assert "## Način rada: cijene i proizvodi" in PROMPT

    @pytest.mark.parametrize(
        "requirement",
        [
            "scrape_url_advanced",   # open the product page
            "Snippet iz pretrage nije izvor",
            "PDV",
            "3 neovisna izvora",
            "Što nisam uspio potvrditi",
        ],
    )
    def test_requires(self, requirement):
        section = PROMPT.split("## Način rada: cijene i proizvodi")[1]
        assert requirement in section


class TestResearchLoop:
    def test_iteration_count_table_is_gone(self):
        # "Standard 3-5 iterations" told the model how often to loop, never what
        # to do in a loop, so it stopped after the first decent answer.
        assert "| Simple (\"What is X?\") | 1-2 |" not in PROMPT

    def test_replaced_by_a_checklist(self):
        rule2 = PROMPT.split("### Rule 2")[1].split("### Rule 3")[0]
        assert "sub-questions" in rule2
        assert "2 independent sources" in rule2
        assert "at most 15 tool calls" in rule2
