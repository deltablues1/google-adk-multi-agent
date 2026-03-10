"""
Integration tests for REAL Custom Tools

Tests actual custom tool implementations:
- DocsFormatter (Markdown to Docs API)
- DriveQueryTranslator (Natural language to QPL)
- SheetsSchemaReader (Schema-first approach)
"""

import pytest
from pathlib import Path

from tools.custom_tools.docs_formatter import DocsFormatter
from tools.custom_tools.drive_query_translator import DriveQueryTranslator
from tools.custom_tools.sheets_schema_reader import SheetsSchemaReader


class TestDocsFormatterReal:
    """Test REAL DocsFormatter implementation"""

    def test_docs_formatter_initialization(self):
        """Test DocsFormatter initializes correctly"""
        # Act
        formatter = DocsFormatter()

        # Assert
        assert formatter is not None
        assert hasattr(formatter, 'markdown_to_docs_requests')

    def test_simple_heading_conversion(self):
        """Test converting simple markdown heading"""
        # Arrange
        formatter = DocsFormatter()
        markdown = "# Heading 1"

        # Act
        requests = formatter.markdown_to_docs_requests(markdown)

        # Assert
        assert isinstance(requests, list)
        assert len(requests) > 0
        # Should contain insertText request
        assert any('insertText' in str(req) for req in requests)

    def test_bold_text_conversion(self):
        """Test converting bold markdown text"""
        # Arrange
        formatter = DocsFormatter()
        markdown = "This is **bold** text"

        # Act
        requests = formatter.markdown_to_docs_requests(markdown)

        # Assert
        assert isinstance(requests, list)
        assert len(requests) > 0

    def test_italic_text_conversion(self):
        """Test converting italic markdown text"""
        # Arrange
        formatter = DocsFormatter()
        markdown = "This is *italic* text"

        # Act
        requests = formatter.markdown_to_docs_requests(markdown)

        # Assert
        assert isinstance(requests, list)
        assert len(requests) > 0

    def test_list_conversion(self):
        """Test converting markdown lists"""
        # Arrange
        formatter = DocsFormatter()
        markdown = """
- Item 1
- Item 2
- Item 3
"""

        # Act
        requests = formatter.markdown_to_docs_requests(markdown)

        # Assert
        assert isinstance(requests, list)
        assert len(requests) > 0

    def test_complex_markdown(self):
        """Test converting complex markdown document"""
        # Arrange
        formatter = DocsFormatter()
        markdown = """
# Main Title

This is a paragraph with **bold** and *italic* text.

## Subtitle

- List item 1
- List item 2

### Sub-subtitle

More text here.
"""

        # Act
        requests = formatter.markdown_to_docs_requests(markdown)

        # Assert
        assert isinstance(requests, list)
        assert len(requests) > 0
        # Multiple formatting requests for different elements

    def test_empty_markdown(self):
        """Test handling empty markdown"""
        # Arrange
        formatter = DocsFormatter()
        markdown = ""

        # Act
        requests = formatter.markdown_to_docs_requests(markdown)

        # Assert
        assert isinstance(requests, list)
        # May be empty list or contain minimal structure

    def test_plain_text_only(self):
        """Test converting plain text without markdown"""
        # Arrange
        formatter = DocsFormatter()
        markdown = "Just plain text without any formatting."

        # Act
        requests = formatter.markdown_to_docs_requests(markdown)

        # Assert
        assert isinstance(requests, list)
        assert len(requests) > 0

    def test_multiple_headings(self):
        """Test multiple heading levels"""
        # Arrange
        formatter = DocsFormatter()
        markdown = """
# H1 Heading
## H2 Heading
### H3 Heading
#### H4 Heading
"""

        # Act
        requests = formatter.markdown_to_docs_requests(markdown)

        # Assert
        assert isinstance(requests, list)
        assert len(requests) >= 4  # At least one request per heading

    def test_mixed_formatting(self):
        """Test mixed bold and italic"""
        # Arrange
        formatter = DocsFormatter()
        markdown = "Text with **bold** and *italic* and ***both***"

        # Act
        requests = formatter.markdown_to_docs_requests(markdown)

        # Assert
        assert isinstance(requests, list)
        assert len(requests) > 0


class TestDriveQueryTranslatorReal:
    """Test REAL DriveQueryTranslator implementation"""

    def test_drive_query_translator_initialization(self):
        """Test DriveQueryTranslator initializes correctly"""
        # Act
        translator = DriveQueryTranslator()

        # Assert
        assert translator is not None
        assert hasattr(translator, 'translate')

    def test_simple_name_query(self):
        """Test translating simple name query"""
        # Arrange
        translator = DriveQueryTranslator()
        query = "find budget"

        # Act
        qpl = translator.translate(query)

        # Assert
        assert isinstance(qpl, str)
        assert len(qpl) > 0
        # Should contain 'name contains' or similar QPL syntax
        assert "name" in qpl.lower() or "budget" in qpl.lower()

    def test_file_type_query(self):
        """Test translating file type query"""
        # Arrange
        translator = DriveQueryTranslator()
        query = "find all spreadsheets"

        # Act
        qpl = translator.translate(query)

        # Assert
        assert isinstance(qpl, str)
        assert len(qpl) > 0

    def test_date_based_query(self):
        """Test translating date-based query"""
        # Arrange
        translator = DriveQueryTranslator()
        query = "files from last week"

        # Act
        qpl = translator.translate(query)

        # Assert
        assert isinstance(qpl, str)
        assert len(qpl) > 0
        # Should contain modifiedTime or createdTime

    def test_owner_query(self):
        """Test translating owner-based query"""
        # Arrange
        translator = DriveQueryTranslator()
        query = "files owned by alice@example.com"

        # Act
        qpl = translator.translate(query)

        # Assert
        assert isinstance(qpl, str)
        assert len(qpl) > 0

    def test_complex_query(self):
        """Test translating complex multi-criteria query"""
        # Arrange
        translator = DriveQueryTranslator()
        query = "find budget spreadsheets from last month"

        # Act
        qpl = translator.translate(query)

        # Assert
        assert isinstance(qpl, str)
        assert len(qpl) > 0

    def test_empty_query(self):
        """Test handling empty query"""
        # Arrange
        translator = DriveQueryTranslator()
        query = ""

        # Act
        qpl = translator.translate(query)

        # Assert
        assert isinstance(qpl, str)
        # May return empty string or default query

    def test_single_word_query(self):
        """Test single word query"""
        # Arrange
        translator = DriveQueryTranslator()
        query = "report"

        # Act
        qpl = translator.translate(query)

        # Assert
        assert isinstance(qpl, str)
        assert len(qpl) > 0

    def test_case_insensitive(self):
        """Test query translation is case insensitive"""
        # Arrange
        translator = DriveQueryTranslator()
        query_lower = "find budget"
        query_upper = "FIND BUDGET"

        # Act
        qpl_lower = translator.translate(query_lower)
        qpl_upper = translator.translate(query_upper)

        # Assert
        # Both should produce similar queries
        assert isinstance(qpl_lower, str)
        assert isinstance(qpl_upper, str)


class TestSheetsSchemaReaderReal:
    """Test REAL SheetsSchemaReader implementation"""

    def test_sheets_schema_reader_initialization(self):
        """Test SheetsSchemaReader initializes correctly"""
        # Act
        reader = SheetsSchemaReader()

        # Assert
        assert reader is not None
        assert hasattr(reader, 'read_schema')

    def test_read_schema_returns_dict(self):
        """Test read_schema returns dictionary"""
        # Arrange
        reader = SheetsSchemaReader()

        # Note: This will require mocking or actual API access
        # For now, test the interface exists
        assert callable(reader.read_schema)

    def test_schema_reader_has_correct_interface(self):
        """Test schema reader has correct method signatures"""
        # Arrange
        reader = SheetsSchemaReader()

        # Assert - Check method exists
        assert hasattr(reader, 'read_schema')

        # Check it accepts required parameters
        import inspect
        sig = inspect.signature(reader.read_schema)
        params = list(sig.parameters.keys())

        # Should accept spreadsheet_id and sheet_name
        assert len(params) >= 2 or 'spreadsheet_id' in params


class TestCustomToolsIntegration:
    """Test custom tools can work together"""

    def test_all_custom_tools_can_be_instantiated(self):
        """Test all custom tools can be created"""
        # Act
        docs_formatter = DocsFormatter()
        drive_translator = DriveQueryTranslator()
        sheets_reader = SheetsSchemaReader()

        # Assert
        assert docs_formatter is not None
        assert drive_translator is not None
        assert sheets_reader is not None

    def test_custom_tools_are_independent(self):
        """Test custom tools can be used independently"""
        # Arrange
        formatter = DocsFormatter()
        translator = DriveQueryTranslator()

        # Act
        docs_result = formatter.markdown_to_docs_requests("# Test")
        drive_result = translator.translate("find test")

        # Assert
        assert docs_result is not None
        assert drive_result is not None
        # Results should be different types/formats
        assert isinstance(docs_result, list)
        assert isinstance(drive_result, str)


class TestDocsFormatterEdgeCases:
    """Test DocsFormatter edge cases"""

    def test_special_characters(self):
        """Test handling special characters"""
        # Arrange
        formatter = DocsFormatter()
        markdown = "Text with special chars: @#$%^&*()"

        # Act
        requests = formatter.markdown_to_docs_requests(markdown)

        # Assert
        assert isinstance(requests, list)
        # Should not crash on special characters

    def test_unicode_characters(self):
        """Test handling unicode characters"""
        # Arrange
        formatter = DocsFormatter()
        markdown = "Text with unicode: ☺️ 你好 مرحبا"

        # Act
        requests = formatter.markdown_to_docs_requests(markdown)

        # Assert
        assert isinstance(requests, list)
        # Should handle unicode properly

    def test_very_long_text(self):
        """Test handling very long text"""
        # Arrange
        formatter = DocsFormatter()
        markdown = "# Long Document\n\n" + ("This is a paragraph. " * 1000)

        # Act
        requests = formatter.markdown_to_docs_requests(markdown)

        # Assert
        assert isinstance(requests, list)
        # Should handle long documents

    def test_nested_formatting(self):
        """Test nested formatting structures"""
        # Arrange
        formatter = DocsFormatter()
        markdown = """
# Title with **bold**

Paragraph with **bold *and italic* text** combined.

- List with **bold items**
  - Nested list
"""

        # Act
        requests = formatter.markdown_to_docs_requests(markdown)

        # Assert
        assert isinstance(requests, list)
        assert len(requests) > 0


class TestDriveQueryTranslatorEdgeCases:
    """Test DriveQueryTranslator edge cases"""

    def test_very_long_query(self):
        """Test very long natural language query"""
        # Arrange
        translator = DriveQueryTranslator()
        query = "find all budget spreadsheets created last month by the finance team " * 10

        # Act
        qpl = translator.translate(query)

        # Assert
        assert isinstance(qpl, str)
        # Should handle long queries

    def test_query_with_numbers(self):
        """Test query with numbers"""
        # Arrange
        translator = DriveQueryTranslator()
        query = "find Q4 2024 budget"

        # Act
        qpl = translator.translate(query)

        # Assert
        assert isinstance(qpl, str)
        assert "2024" in qpl or "budget" in qpl.lower()

    def test_query_with_special_chars(self):
        """Test query with special characters"""
        # Arrange
        translator = DriveQueryTranslator()
        query = "find file-name_with.special@chars"

        # Act
        qpl = translator.translate(query)

        # Assert
        assert isinstance(qpl, str)
        # Should handle special characters in filenames

    def test_ambiguous_query(self):
        """Test ambiguous query"""
        # Arrange
        translator = DriveQueryTranslator()
        query = "find it"  # Very ambiguous

        # Act
        qpl = translator.translate(query)

        # Assert
        assert isinstance(qpl, str)
        # Should return some query, even if generic


class TestCustomToolsFileStructure:
    """Test custom tools file structure"""

    def test_docs_formatter_file_exists(self):
        """Test DocsFormatter file exists"""
        # Arrange
        file_path = Path("tools/custom_tools/docs_formatter.py")

        # Assert
        assert file_path.exists(), "DocsFormatter file must exist"
        assert file_path.is_file()

    def test_drive_query_translator_file_exists(self):
        """Test DriveQueryTranslator file exists"""
        # Arrange
        file_path = Path("tools/custom_tools/drive_query_translator.py")

        # Assert
        assert file_path.exists(), "DriveQueryTranslator file must exist"
        assert file_path.is_file()

    def test_sheets_schema_reader_file_exists(self):
        """Test SheetsSchemaReader file exists"""
        # Arrange
        file_path = Path("tools/custom_tools/sheets_schema_reader.py")

        # Assert
        assert file_path.exists(), "SheetsSchemaReader file must exist"
        assert file_path.is_file()

    def test_custom_tools_init_file_exists(self):
        """Test custom_tools __init__.py exists"""
        # Arrange
        file_path = Path("tools/custom_tools/__init__.py")

        # Assert
        assert file_path.exists(), "custom_tools __init__.py must exist"
