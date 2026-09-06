"""
Google Docs Formatter - Custom Tool

Konvertira Markdown u Google Docs API batch update zahtjeve.
Omogućava LLM-u da kreira strukturirane i formatirane dokumente bez
direktnog korištenja složenog Docs API-ja.
"""

from typing import Dict, List, Any, Optional
import re
import logging

logger = logging.getLogger(__name__)


def _is_table_separator(line: str) -> bool:
    """The |---|:--:| row that turns two lines into a table."""
    stripped = line.strip()
    if not stripped.startswith("|"):
        return False
    cells = _split_row(stripped)
    return bool(cells) and all(
        re.fullmatch(r":?-{1,}:?", c.strip()) for c in cells if c.strip()
    )


def _split_row(line: str) -> List[str]:
    """Cells of one markdown table row, without the outer pipes."""
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [c.strip() for c in stripped.split("|")]


def split_markdown_blocks(markdown: str) -> List[Dict[str, Any]]:
    """Split markdown into text blocks and table blocks.

    Tables are pulled out because Google Docs has no markdown: a table has
    to be created as a real table element and its cells filled by index.
    Left in the text stream they render as rows of pipe characters, which
    is exactly what a 14,000-character report came out looking like on
    2026-09-06.

    A table needs a header row, a separator row, and at least one body row;
    anything less stays text, because a lone pipe is usually just a pipe.
    """
    lines = markdown.split("\n")
    blocks: List[Dict[str, Any]] = []
    text: List[str] = []
    i = 0

    def flush_text():
        if text:
            blocks.append({"kind": "text", "content": "\n".join(text)})
            text.clear()

    while i < len(lines):
        line = lines[i]
        is_start = (
            i + 2 < len(lines)
            and line.strip().startswith("|")
            and _is_table_separator(lines[i + 1])
            and lines[i + 2].strip().startswith("|")
        )
        if not is_start:
            text.append(line)
            i += 1
            continue

        header = _split_row(line)
        rows = []
        j = i + 2
        while j < len(lines) and lines[j].strip().startswith("|"):
            cells = _split_row(lines[j])
            # Pad or trim so every row matches the header width; Docs tables
            # are rectangular and a ragged row would shift every later cell.
            cells = (cells + [""] * len(header))[: len(header)]
            rows.append(cells)
            j += 1

        flush_text()
        blocks.append({"kind": "table", "header": header, "rows": rows})
        i = j

    flush_text()
    return [b for b in blocks if b["kind"] != "text" or b["content"].strip()]


class DocsFormatter:
    """
    Konverter Markdown -> Google Docs API batch update zahtjevi

    Podržava:
    - Headings (H1-H6)
    - Bold, Italic, Underline
    - Lists (ordered, unordered)
    - Links
    - Paragraphs
    """

    def __init__(self):
        self.requests: List[Dict[str, Any]] = []
        self.current_index = 1  # Docs start index (1-based)

    def markdown_to_docs_requests(self, markdown: str) -> List[Dict[str, Any]]:
        """
        Konvertira Markdown tekst u Google Docs API batch update zahtjeve

        Args:
            markdown: Markdown tekst

        Returns:
            Lista batch update request objekata
        """
        self.requests = []
        self.current_index = 1

        lines = markdown.split('\n')

        for line in lines:
            line = line.rstrip()

            # Prazan red
            if not line:
                self._add_paragraph("\n")
                continue

            # Heading
            if line.startswith('#'):
                self._process_heading(line)
            # Unordered list
            elif line.startswith('- ') or line.startswith('* '):
                self._process_list_item(line, ordered=False)
            # Ordered list
            elif re.match(r'^\d+\.\s', line):
                self._process_list_item(line, ordered=True)
            # Paragraph
            else:
                self._process_paragraph(line)

        return self.requests

    def _process_heading(self, line: str) -> None:
        """Procesira heading liniju"""
        match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if not match:
            return

        level = len(match.group(1))
        text = match.group(2)

        # Insert text
        self.requests.append({
            'insertText': {
                'location': {'index': self.current_index},
                'text': text + '\n'
            }
        })

        # Apply heading style
        end_index = self.current_index + len(text)
        self.requests.append({
            'updateParagraphStyle': {
                'range': {
                    'startIndex': self.current_index,
                    'endIndex': end_index
                },
                'paragraphStyle': {
                    'namedStyleType': f'HEADING_{level}'
                },
                'fields': 'namedStyleType'
            }
        })

        self.current_index = end_index + 1

    def _process_paragraph(self, line: str) -> None:
        """Procesira obični paragraf s inline formatiranjem"""
        # Parse inline formatting (bold, italic, links)
        segments = self._parse_inline_formatting(line)

        start_index = self.current_index

        # Insert text
        self.requests.append({
            'insertText': {
                'location': {'index': self.current_index},
                'text': line + '\n'
            }
        })

        # Apply inline formatting
        offset = self.current_index
        for segment in segments:
            if segment['type'] != 'plain':
                self._apply_text_style(
                    start=offset + segment['start'],
                    end=offset + segment['end'],
                    style_type=segment['type']
                )

        self.current_index += len(line) + 1

    def _process_list_item(self, line: str, ordered: bool) -> None:
        """Procesira list item"""
        # Remove list marker
        if ordered:
            text = re.sub(r'^\d+\.\s+', '', line)
        else:
            text = re.sub(r'^[-*]\s+', '', line)

        # Insert text
        self.requests.append({
            'insertText': {
                'location': {'index': self.current_index},
                'text': text + '\n'
            }
        })

        # Apply list formatting
        end_index = self.current_index + len(text)
        self.requests.append({
            'createParagraphBullets': {
                'range': {
                    'startIndex': self.current_index,
                    'endIndex': end_index
                },
                'bulletPreset': 'NUMBERED_DECIMAL_ALPHA_ROMAN' if ordered else 'BULLET_DISC_CIRCLE_SQUARE'
            }
        })

        self.current_index = end_index + 1

    def _add_paragraph(self, text: str) -> None:
        """Dodaje običan paragraf"""
        self.requests.append({
            'insertText': {
                'location': {'index': self.current_index},
                'text': text
            }
        })
        self.current_index += len(text)

    def _parse_inline_formatting(self, text: str) -> List[Dict[str, Any]]:
        """
        Parsira inline formatiranje (bold, italic, links)

        Returns:
            Lista segmenata s tipom formatiranja i pozicijom
        """
        segments = []

        # Bold: **text** ili __text__
        for match in re.finditer(r'\*\*(.+?)\*\*|__(.+?)__', text):
            segments.append({
                'type': 'bold',
                'start': match.start(),
                'end': match.end(),
                'text': match.group(1) or match.group(2)
            })

        # Italic: *text* ili _text_
        for match in re.finditer(r'\*(.+?)\*|_(.+?)_', text):
            # Skip if part of bold
            if not any(s['start'] <= match.start() < s['end'] for s in segments):
                segments.append({
                    'type': 'italic',
                    'start': match.start(),
                    'end': match.end(),
                    'text': match.group(1) or match.group(2)
                })

        # Links: [text](url)
        for match in re.finditer(r'\[(.+?)\]\((.+?)\)', text):
            segments.append({
                'type': 'link',
                'start': match.start(),
                'end': match.end(),
                'text': match.group(1),
                'url': match.group(2)
            })

        return segments

    def _apply_text_style(self, start: int, end: int, style_type: str) -> None:
        """Primjenjuje text style na range"""
        if style_type == 'bold':
            self.requests.append({
                'updateTextStyle': {
                    'range': {'startIndex': start, 'endIndex': end},
                    'textStyle': {'bold': True},
                    'fields': 'bold'
                }
            })
        elif style_type == 'italic':
            self.requests.append({
                'updateTextStyle': {
                    'range': {'startIndex': start, 'endIndex': end},
                    'textStyle': {'italic': True},
                    'fields': 'italic'
                }
            })
        elif style_type == 'underline':
            self.requests.append({
                'updateTextStyle': {
                    'range': {'startIndex': start, 'endIndex': end},
                    'textStyle': {'underline': True},
                    'fields': 'underline'
                }
            })


def format_markdown_for_docs(credentials=None, markdown: str = "") -> List[Dict[str, Any]]:
    """
    Helper funkcija za formatiranje Markdown-a za Google Docs

    Args:
        credentials: OAuth credentials (ignored, tool doesn't need auth)
        markdown: Markdown tekst

    Returns:
        Lista batch update zahtjeva za Google Docs API
    """
    formatter = DocsFormatter()
    return formatter.markdown_to_docs_requests(markdown)


# Function declaration za ADK
def get_docs_formatter_tool():
    """
    Vraća Tool sa Docs Formatter FunctionDeclaration

    Returns:
        Tool objekt
    """
    from google.genai.types import Tool, FunctionDeclaration

    return Tool(
        function_declarations=[
            FunctionDeclaration(
                name="format_markdown_for_docs",
                description=(
                    "Convert Markdown text to Google Docs API batch update requests. "
                    "Supports headings, bold, italic, lists, and links. "
                    "Use this to create well-formatted documents instead of plain text."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "markdown": {
                            "type": "string",
                            "description": "Markdown text to convert to Docs format"
                        }
                    },
                    "required": ["markdown"]
                }
            )
        ]
    )
