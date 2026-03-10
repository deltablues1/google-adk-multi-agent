"""
Integration tests for Drive MCP Server

Tests the integration between Librarian agent and Drive MCP toolset using mock server.
"""

import pytest
from unittest.mock import Mock
from typing import Dict, Any

from tests.mocks.mock_mcp_servers import MockDriveMCPServer, create_mock_drive_server


class TestDriveMCPIntegration:
    """Test Drive MCP Server integration"""

    @pytest.fixture
    def mock_drive_server(self):
        """Create mock Drive server fixture"""
        return create_mock_drive_server()

    @pytest.fixture
    def librarian_agent_mock(self):
        """Create mock Librarian agent"""
        agent = Mock()
        agent.name = "librarian"
        agent.model = "gemini-1.5-flash"
        return agent

    def test_search_files_by_name(self, mock_drive_server):
        """Test searching files by name"""
        # Act
        results = mock_drive_server.search_files(query="document")

        # Assert
        assert isinstance(results, list)
        assert len(results) > 0
        assert "test-document.docx" in results[0]["name"]

    def test_search_files_case_insensitive(self, mock_drive_server):
        """Test search is case-insensitive"""
        # Act
        results_lower = mock_drive_server.search_files(query="budget")
        results_upper = mock_drive_server.search_files(query="BUDGET")
        results_mixed = mock_drive_server.search_files(query="BuDgEt")

        # Assert
        assert len(results_lower) == len(results_upper) == len(results_mixed)
        assert results_lower[0]["id"] == results_upper[0]["id"]

    def test_search_files_no_match(self, mock_drive_server):
        """Test search with no matching files"""
        # Act
        results = mock_drive_server.search_files(query="nonexistent-file-xyz")

        # Assert
        assert isinstance(results, list)
        assert len(results) == 0

    def test_search_files_max_results(self, mock_drive_server):
        """Test search respects max_results parameter"""
        # Act
        results_unlimited = mock_drive_server.search_files(query="", max_results=100)
        results_limited = mock_drive_server.search_files(query="", max_results=1)

        # Assert
        assert len(results_limited) <= 1
        assert len(results_limited) <= len(results_unlimited)

    def test_get_file_by_id(self, mock_drive_server):
        """Test getting file details by ID"""
        # Arrange
        file_id = "file-1"

        # Act
        file_data = mock_drive_server.get_file(file_id)

        # Assert
        assert file_data["id"] == file_id
        assert "name" in file_data
        assert "mimeType" in file_data
        assert "owners" in file_data

    def test_get_file_metadata_structure(self, mock_drive_server):
        """Test file metadata has expected structure"""
        # Act
        file_data = mock_drive_server.get_file("file-1")

        # Assert
        assert isinstance(file_data["owners"], list)
        assert len(file_data["owners"]) > 0
        assert "emailAddress" in file_data["owners"][0]

    def test_get_nonexistent_file(self, mock_drive_server):
        """Test getting file that doesn't exist"""
        # Act
        result = mock_drive_server.get_file("nonexistent-file-id")

        # Assert
        assert result == {}

    def test_upload_file(self, mock_drive_server):
        """Test uploading a file"""
        # Arrange
        file_name = "new-report.pdf"
        content = "PDF content here"
        mime_type = "application/pdf"

        # Act
        result = mock_drive_server.upload_file(
            file_name=file_name,
            content=content,
            mime_type=mime_type
        )

        # Assert
        assert result["status"] == "uploaded"
        assert "id" in result

        # Verify file was added
        uploaded_file = mock_drive_server.get_file(result["id"])
        assert uploaded_file["name"] == file_name
        assert uploaded_file["mimeType"] == mime_type
        assert uploaded_file["content"] == content

    def test_upload_multiple_files(self, mock_drive_server):
        """Test uploading multiple files"""
        # Arrange
        initial_count = len(mock_drive_server.files)

        # Act
        result1 = mock_drive_server.upload_file("file1.txt", "content1", "text/plain")
        result2 = mock_drive_server.upload_file("file2.txt", "content2", "text/plain")
        result3 = mock_drive_server.upload_file("file3.txt", "content3", "text/plain")

        # Assert
        assert len(mock_drive_server.files) == initial_count + 3
        assert result1["id"] != result2["id"] != result3["id"]

    def test_search_after_upload(self, mock_drive_server):
        """Test that uploaded files are searchable"""
        # Arrange
        mock_drive_server.upload_file("quarterly-report.docx", "content", "application/vnd.google-apps.document")

        # Act
        results = mock_drive_server.search_files(query="quarterly")

        # Assert
        assert len(results) > 0
        assert any("quarterly-report.docx" in f["name"] for f in results)

    def test_file_mime_types(self, mock_drive_server):
        """Test different file MIME types"""
        # Act
        doc_file = mock_drive_server.get_file("file-1")
        sheet_file = mock_drive_server.get_file("file-2")

        # Assert
        assert "document" in doc_file["mimeType"]
        assert "spreadsheet" in sheet_file["mimeType"]


class TestDriveMCPDataIntegrity:
    """Test data integrity in Drive MCP operations"""

    @pytest.fixture
    def mock_drive_server(self):
        """Create mock Drive server fixture"""
        return create_mock_drive_server()

    def test_file_id_uniqueness(self, mock_drive_server):
        """Test that file IDs are unique"""
        # Act
        ids = []
        for i in range(10):
            result = mock_drive_server.upload_file(
                file_name=f"file{i}.txt",
                content=f"content{i}",
                mime_type="text/plain"
            )
            ids.append(result["id"])

        # Assert
        assert len(ids) == len(set(ids)), "File IDs should be unique"

    def test_uploaded_file_persistence(self, mock_drive_server):
        """Test that uploaded file data persists correctly"""
        # Arrange
        file_data = {
            "file_name": "test-persistence.docx",
            "content": "This is test content",
            "mime_type": "application/vnd.google-apps.document"
        }

        # Act
        result = mock_drive_server.upload_file(**file_data)
        retrieved_file = mock_drive_server.get_file(result["id"])

        # Assert
        assert retrieved_file["name"] == file_data["file_name"]
        assert retrieved_file["content"] == file_data["content"]
        assert retrieved_file["mimeType"] == file_data["mime_type"]

    def test_search_returns_complete_metadata(self, mock_drive_server):
        """Test that search results contain complete file metadata"""
        # Act
        results = mock_drive_server.search_files(query="budget")

        # Assert
        assert len(results) > 0
        for file in results:
            assert "id" in file
            assert "name" in file
            assert "mimeType" in file
            assert "owners" in file


class TestDriveMCPEdgeCases:
    """Test edge cases in Drive MCP integration"""

    @pytest.fixture
    def mock_drive_server(self):
        """Create mock Drive server fixture"""
        return create_mock_drive_server()

    def test_empty_search_query(self, mock_drive_server):
        """Test search with empty query"""
        # Act
        results = mock_drive_server.search_files(query="")

        # Assert
        # Empty query should not crash, may return no results
        assert isinstance(results, list)

    def test_upload_file_with_special_characters(self, mock_drive_server):
        """Test uploading file with special characters in name"""
        # Arrange
        file_name = "report_2024-Q1 (final) [v2].pdf"

        # Act
        result = mock_drive_server.upload_file(
            file_name=file_name,
            content="content",
            mime_type="application/pdf"
        )

        # Assert
        assert result["status"] == "uploaded"
        uploaded_file = mock_drive_server.get_file(result["id"])
        assert uploaded_file["name"] == file_name

    def test_upload_empty_content(self, mock_drive_server):
        """Test uploading file with empty content"""
        # Act
        result = mock_drive_server.upload_file(
            file_name="empty.txt",
            content="",
            mime_type="text/plain"
        )

        # Assert
        assert result["status"] == "uploaded"
        uploaded_file = mock_drive_server.get_file(result["id"])
        assert uploaded_file["content"] == ""

    def test_max_results_zero(self, mock_drive_server):
        """Test search with max_results=0"""
        # Act
        results = mock_drive_server.search_files(query="test", max_results=0)

        # Assert
        assert len(results) == 0

    def test_max_results_negative(self, mock_drive_server):
        """Test search with negative max_results (edge case)"""
        # Act
        results = mock_drive_server.search_files(query="test", max_results=-1)

        # Assert
        # Implementation should handle gracefully (returns empty or all)
        assert isinstance(results, list)
