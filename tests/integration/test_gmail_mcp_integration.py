"""
Integration tests for Gmail MCP Server

Tests the integration between Mailer agent and Gmail MCP toolset using mock server.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

from tests.mocks.mock_mcp_servers import MockGmailMCPServer, create_mock_gmail_server


class TestGmailMCPIntegration:
    """Test Gmail MCP Server integration"""

    @pytest.fixture
    def mock_gmail_server(self):
        """Create mock Gmail server fixture"""
        return create_mock_gmail_server()

    @pytest.fixture
    def mailer_agent_mock(self):
        """Create mock Mailer agent"""
        # We'll mock the agent since we're testing the MCP integration
        agent = Mock()
        agent.name = "mailer"
        agent.model = "gemini-1.5-pro"
        return agent

    def test_send_message_integration(self, mock_gmail_server):
        """Test sending message through mock Gmail server"""
        # Arrange
        to = "recipient@example.com"
        subject = "Test Email"
        body = "This is a test email body"

        # Act
        result = mock_gmail_server.send_message(to=to, subject=subject, body=body)

        # Assert
        assert result["status"] == "sent"
        assert "id" in result
        assert len(mock_gmail_server.sent_messages) == 1

        sent_msg = mock_gmail_server.sent_messages[0]
        assert sent_msg["to"] == to
        assert sent_msg["subject"] == subject
        assert sent_msg["body"] == body

    def test_send_message_with_cc_bcc(self, mock_gmail_server):
        """Test sending message with CC and BCC"""
        # Arrange
        params = {
            "to": "recipient@example.com",
            "subject": "Test with CC/BCC",
            "body": "Test body",
            "cc": "cc@example.com",
            "bcc": "bcc@example.com"
        }

        # Act
        result = mock_gmail_server.send_message(**params)

        # Assert
        assert result["status"] == "sent"
        sent_msg = mock_gmail_server.sent_messages[0]
        assert sent_msg["cc"] == params["cc"]
        assert sent_msg["bcc"] == params["bcc"]

    def test_search_threads(self, mock_gmail_server):
        """Test searching email threads"""
        # Act
        results = mock_gmail_server.search_threads(query="test", max_results=10)

        # Assert
        assert isinstance(results, list)
        assert len(results) > 0
        assert "id" in results[0]
        assert "snippet" in results[0]

    def test_get_thread_details(self, mock_gmail_server):
        """Test getting thread details"""
        # Arrange
        thread_id = "thread-1"

        # Act
        thread = mock_gmail_server.get_thread(thread_id)

        # Assert
        assert thread["id"] == thread_id
        assert "messages" in thread
        assert len(thread["messages"]) > 0

        # Check message structure
        msg = thread["messages"][0]
        assert "id" in msg
        assert "from" in msg
        assert "to" in msg
        assert "subject" in msg
        assert "body" in msg

    def test_get_nonexistent_thread(self, mock_gmail_server):
        """Test getting thread that doesn't exist"""
        # Act
        result = mock_gmail_server.get_thread("nonexistent-thread-id")

        # Assert
        assert result == {}

    def test_create_draft(self, mock_gmail_server):
        """Test creating email draft"""
        # Arrange
        to = "recipient@example.com"
        subject = "Draft Email"
        body = "This is a draft"

        # Act
        result = mock_gmail_server.create_draft(to=to, subject=subject, body=body)

        # Assert
        assert result["status"] == "draft"
        assert "id" in result
        assert len(mock_gmail_server.drafts) == 1

        draft = mock_gmail_server.drafts[0]
        assert draft["to"] == to
        assert draft["subject"] == subject
        assert draft["body"] == body

    def test_multiple_messages_sent(self, mock_gmail_server):
        """Test sending multiple messages"""
        # Act
        result1 = mock_gmail_server.send_message(
            to="user1@example.com",
            subject="Message 1",
            body="Body 1"
        )
        result2 = mock_gmail_server.send_message(
            to="user2@example.com",
            subject="Message 2",
            body="Body 2"
        )
        result3 = mock_gmail_server.send_message(
            to="user3@example.com",
            subject="Message 3",
            body="Body 3"
        )

        # Assert
        assert len(mock_gmail_server.sent_messages) == 3
        assert result1["id"] != result2["id"]
        assert result2["id"] != result3["id"]

        # Verify each message
        assert mock_gmail_server.sent_messages[0]["to"] == "user1@example.com"
        assert mock_gmail_server.sent_messages[1]["to"] == "user2@example.com"
        assert mock_gmail_server.sent_messages[2]["to"] == "user3@example.com"

    def test_search_with_max_results_limit(self, mock_gmail_server):
        """Test search respects max_results limit"""
        # Act
        results_unlimited = mock_gmail_server.search_threads(query="test")
        results_limited = mock_gmail_server.search_threads(query="test", max_results=1)

        # Assert
        assert len(results_limited) <= 1
        assert len(results_limited) <= len(results_unlimited)

    def test_draft_and_message_independence(self, mock_gmail_server):
        """Test that drafts and sent messages are tracked separately"""
        # Act
        mock_gmail_server.send_message(
            to="user@example.com",
            subject="Sent Message",
            body="Sent"
        )
        mock_gmail_server.create_draft(
            to="user@example.com",
            subject="Draft Message",
            body="Draft"
        )

        # Assert
        assert len(mock_gmail_server.sent_messages) == 1
        assert len(mock_gmail_server.drafts) == 1
        assert mock_gmail_server.sent_messages[0]["subject"] == "Sent Message"
        assert mock_gmail_server.drafts[0]["subject"] == "Draft Message"


class TestGmailMCPErrorHandling:
    """Test error handling in Gmail MCP integration"""

    @pytest.fixture
    def mock_gmail_server(self):
        """Create mock Gmail server fixture"""
        return create_mock_gmail_server()

    def test_empty_search_query(self, mock_gmail_server):
        """Test search with empty query"""
        # Act
        results = mock_gmail_server.search_threads(query="")

        # Assert
        # Should not crash, returns results (mock doesn't filter by query)
        assert isinstance(results, list)

    def test_send_message_minimal_params(self, mock_gmail_server):
        """Test sending message with only required parameters"""
        # Act
        result = mock_gmail_server.send_message(
            to="user@example.com",
            subject="Test",
            body="Body"
        )

        # Assert
        assert result["status"] == "sent"
        assert "id" in result


class TestGmailMCPDataIntegrity:
    """Test data integrity in Gmail MCP operations"""

    @pytest.fixture
    def mock_gmail_server(self):
        """Create mock Gmail server fixture"""
        return create_mock_gmail_server()

    def test_message_id_uniqueness(self, mock_gmail_server):
        """Test that message IDs are unique"""
        # Act
        ids = []
        for i in range(10):
            result = mock_gmail_server.send_message(
                to=f"user{i}@example.com",
                subject=f"Message {i}",
                body=f"Body {i}"
            )
            ids.append(result["id"])

        # Assert
        assert len(ids) == len(set(ids)), "Message IDs should be unique"

    def test_draft_id_uniqueness(self, mock_gmail_server):
        """Test that draft IDs are unique"""
        # Act
        ids = []
        for i in range(10):
            result = mock_gmail_server.create_draft(
                to=f"user{i}@example.com",
                subject=f"Draft {i}",
                body=f"Body {i}"
            )
            ids.append(result["id"])

        # Assert
        assert len(ids) == len(set(ids)), "Draft IDs should be unique"

    def test_message_data_persistence(self, mock_gmail_server):
        """Test that sent message data is persisted correctly"""
        # Arrange
        original_data = {
            "to": "recipient@example.com",
            "subject": "Important Email",
            "body": "This is important content",
            "cc": "cc@example.com",
            "priority": "high"
        }

        # Act
        result = mock_gmail_server.send_message(**original_data)
        persisted_msg = mock_gmail_server.sent_messages[0]

        # Assert
        for key, value in original_data.items():
            assert persisted_msg[key] == value, f"{key} should match original data"
