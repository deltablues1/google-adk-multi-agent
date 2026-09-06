"""A markdown table has to become a real table, not a row of pipe characters.

Google Docs has no markdown. DocsFormatter handled headings, lists and
paragraphs, and everything else fell through to a plain paragraph -- so a
table written by the synthesizer arrived in the document as "| Zona | Opis |"
lines. Reported 2026-09-06 on the Ex zones document as "tablice su nikakve",
after Opus had spent two minutes writing a perfectly good one.

The dangerous part is not the parsing but the indices: every insert shifts
everything after it, and an off-by-one writes the report into the wrong cells
without failing. So cells are read back from the document and filled from the
LAST index to the first, which nothing before them can move.

Run with:
    pytest tests/unit/test_docs_tables.py -v
"""

import pytest

from tools.adk_tools import docs_adk_tools as dt
from tools.custom_tools.docs_formatter import split_markdown_blocks

MD = """# Klasifikacija

Uvodni tekst o zonama.

| Zona | Prisutnost | Kategorija |
|------|:----------:|-----------:|
| 20 | stalno | 1D |
| 21 | povremeno | 2D |

Zakljucak na kraju.
"""


class TestSplitting:
    def test_the_table_is_lifted_out_of_the_text(self):
        blocks = split_markdown_blocks(MD)
        kinds = [b["kind"] for b in blocks]
        assert kinds == ["text", "table", "text"]

    def test_header_and_rows_are_parsed(self):
        table = [b for b in split_markdown_blocks(MD) if b["kind"] == "table"][0]
        assert table["header"] == ["Zona", "Prisutnost", "Kategorija"]
        assert table["rows"] == [["20", "stalno", "1D"], ["21", "povremeno", "2D"]]

    def test_alignment_markers_do_not_become_a_row(self):
        table = [b for b in split_markdown_blocks(MD) if b["kind"] == "table"][0]
        assert all("---" not in c for row in table["rows"] for c in row)

    def test_a_ragged_row_is_squared_off(self):
        """Docs tables are rectangular; a short row would shift every cell."""
        md = "| a | b | c |\n|---|---|---|\n| 1 |\n| 1 | 2 | 3 | 4 |\n"
        table = split_markdown_blocks(md)[0]
        assert [len(r) for r in table["rows"]] == [3, 3]

    def test_a_lone_pipe_stays_text(self):
        md = "Vrijednost | jedinica su odvojeni crtom.\n"
        assert [b["kind"] for b in split_markdown_blocks(md)] == ["text"]

    def test_a_table_without_body_rows_stays_text(self):
        md = "| a | b |\n|---|---|\n"
        assert [b["kind"] for b in split_markdown_blocks(md)] == ["text"]


class FakeDocs:
    """Enough of the Docs API to watch the index arithmetic."""

    def __init__(self):
        self.batches = []
        self.table_cells = []

    async def get(self, creds, document_id):
        content = [{"endIndex": 100}]
        if self.table_cells:
            rows = []
            for row in self.table_cells:
                rows.append({"tableCells": [{"content": [{"startIndex": i}]} for i in row]})
            content.append({"table": {"tableRows": rows}})
            content.append({"endIndex": 400})
        return {"body": {"content": content}}

    async def batch(self, creds, document_id, requests):
        self.batches.append(requests)
        for r in requests:
            if "insertTable" in r:
                spec = r["insertTable"]
                base = 200
                self.table_cells = [
                    [base + (row * spec["columns"] + col) * 10
                     for col in range(spec["columns"])]
                    for row in range(spec["rows"])
                ]
        return {"status": "ok"}


@pytest.fixture
def fake(monkeypatch):
    api = FakeDocs()
    monkeypatch.setattr(dt, "_get_credentials", lambda: object())
    monkeypatch.setattr(
        "tools.api_implementations.docs_api.docs_get_document", api.get, raising=False
    )
    monkeypatch.setattr(
        "tools.api_implementations.docs_api.docs_batch_update", api.batch, raising=False
    )
    return api


class TestWritingTheTable:
    @pytest.mark.asyncio
    async def test_it_reports_what_it_wrote(self, fake):
        result = await dt.docs_write_markdown("doc-1", MD)
        assert result["status"] == "ok"
        assert result["tables"] == 1
        assert result["blocks"] == 3

    @pytest.mark.asyncio
    async def test_a_real_table_element_is_created(self, fake):
        await dt.docs_write_markdown("doc-1", MD)
        inserts = [r for b in fake.batches for r in b if "insertTable" in r]
        assert len(inserts) == 1
        spec = inserts[0]["insertTable"]
        assert spec["rows"] == 3, "header plus two body rows"
        assert spec["columns"] == 3

    @pytest.mark.asyncio
    async def test_cells_are_filled_from_the_last_index_backwards(self, fake):
        """The whole reason this reads the document back.

        Cell indices in the fake run 200..280; the trailing text block
        lands near 399 and is deliberately excluded here.
        """
        await dt.docs_write_markdown("doc-1", MD)
        fills = [
            r for b in fake.batches for r in b
            if "insertText" in r and 200 <= r["insertText"]["location"]["index"] <= 280
        ]
        indices = [r["insertText"]["location"]["index"] for r in fills]
        assert indices == sorted(indices, reverse=True), (
            "filling forwards would shift every later cell"
        )

    @pytest.mark.asyncio
    async def test_every_cell_gets_its_own_value(self, fake):
        await dt.docs_write_markdown("doc-1", MD)
        written = {
            r["insertText"]["text"]
            for b in fake.batches for r in b
            if "insertText" in r and 200 <= r["insertText"]["location"]["index"] <= 280
        }
        assert written == {
            "Zona", "Prisutnost", "Kategorija",
            "20", "stalno", "1D",
            "21", "povremeno", "2D",
        }

    @pytest.mark.asyncio
    async def test_the_header_row_is_bolded(self, fake):
        await dt.docs_write_markdown("doc-1", MD)
        bolds = [r for b in fake.batches for r in b if "updateTextStyle" in r]
        assert len(bolds) == 3, "one per header cell"
        assert all(r["updateTextStyle"]["textStyle"]["bold"] for r in bolds)

    @pytest.mark.asyncio
    async def test_no_pipe_characters_reach_the_document(self, fake):
        await dt.docs_write_markdown("doc-1", MD)
        texts = [
            r["insertText"]["text"]
            for b in fake.batches for r in b if "insertText" in r
        ]
        assert not any("|" in t for t in texts), "this is the reported bug"


class TestFailuresAreHonest:
    @pytest.mark.asyncio
    async def test_a_lost_answer_is_unknown_not_failed(self, fake, monkeypatch):
        from tools.resilience.retry_handler import UnconfirmedWrite

        async def lose(*a, **kw):
            raise UnconfirmedWrite("connection reset")

        monkeypatch.setattr(
            "tools.api_implementations.docs_api.docs_batch_update", lose, raising=False
        )
        result = await dt.docs_write_markdown("doc-1", MD)
        assert result["outcome"] == "unknown"
