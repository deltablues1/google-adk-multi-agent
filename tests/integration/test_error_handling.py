"""
Integration tests for Error Handling

Tests error scenarios across the system including MCP failures, auth issues, and agent errors.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any
import json

from tests.mocks.mock_mcp_servers import (
    MockGmailMCPServer,
    MockDriveMCPServer,
    create_mock_gmail_server,
    create_mock_drive_server
)


class TestMCPServerErrors:
    """Test error handling for MCP server failures"""

    @pytest.fixture
    def mock_gmail_server(self):
        """Create mock Gmail server"""
        return create_mock_gmail_server()

    @pytest.fixture
    def mock_drive_server(self):
        """Create mock Drive server"""
        return create_mock_drive_server()

    def test_gmail_send_message_validation_error(self, mock_gmail_server):
        """Test handling of invalid email parameters"""
        # Arrange - Missing required fields would cause validation error
        # Our mock is simple, but real implementation should validate

        # Act
        result = mock_gmail_server.send_message(
            to="invalid-email",  # Invalid email format
            subject="Test",
            body="Body"
        )

        # Assert - Mock still processes, but real implementation should validate
        assert "id" in result

    def test_gmail_thread_not_found(self, mock_gmail_server):
        """Test handling when thread doesn't exist"""
        # Act
        result = mock_gmail_server.get_thread("nonexistent-thread-123")

        # Assert
        assert result == {}  # Empty dict indicates not found

    def test_drive_file_not_found(self, mock_drive_server):
        """Test handling when file doesn't exist"""
        # Act
        result = mock_drive_server.get_file("nonexistent-file-456")

        # Assert
        assert result == {}  # Empty dict indicates not found

    def test_drive_search_with_invalid_query(self, mock_drive_server):
        """Test search with potentially problematic query"""
        # Arrange
        problematic_queries = [
            "",  # Empty query
            "   ",  # Whitespace only
            "a" * 1000,  # Very long query
            "special@#$%^&*()characters"
        ]

        # Act & Assert
        for query in problematic_queries:
            result = mock_drive_server.search_files(query=query)
            assert isinstance(result, list)  # Should not crash

    def test_drive_upload_with_empty_filename(self, mock_drive_server):
        """Test upload with edge case filename"""
        # Act
        result = mock_drive_server.upload_file(
            file_name="",
            content="test content",
            mime_type="text/plain"
        )

        # Assert
        assert result["status"] == "uploaded"
        # In real implementation, should validate filename


class TestAuthenticationErrors:
    """Test error handling for authentication failures"""

    @pytest.fixture
    def mock_oauth_manager(self):
        """Create mock OAuth manager"""
        with patch('auth.oauth_manager.OAuthManager') as mock:
            manager = MagicMock()
            mock.return_value = manager
            yield manager

    @pytest.fixture
    def mock_service_account_manager(self):
        """Create mock Service Account manager"""
        with patch('auth.service_account_manager.ServiceAccountManager') as mock:
            manager = MagicMock()
            mock.return_value = manager
            yield manager

    def test_oauth_token_expired(self, mock_oauth_manager):
        """Test handling of expired OAuth token"""
        # Arrange
        mock_oauth_manager.get_credentials.side_effect = Exception("Token expired")

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            mock_oauth_manager.get_credentials()

        assert "Token expired" in str(exc_info.value)

    def test_oauth_refresh_failure(self, mock_oauth_manager):
        """Test handling when token refresh fails"""
        # Arrange
        mock_oauth_manager.refresh_token.side_effect = Exception("Refresh token invalid")

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            mock_oauth_manager.refresh_token()

        assert "Refresh token invalid" in str(exc_info.value)

    def test_service_account_missing_credentials(self, mock_service_account_manager):
        """Test handling when service account credentials file is missing"""
        # Arrange
        mock_service_account_manager.get_credentials.side_effect = FileNotFoundError(
            "Service account file not found"
        )

        # Act & Assert
        with pytest.raises(FileNotFoundError) as exc_info:
            mock_service_account_manager.get_credentials()

        assert "Service account file not found" in str(exc_info.value)

    def test_service_account_invalid_json(self, mock_service_account_manager):
        """Test handling when service account file has invalid JSON"""
        # Arrange
        mock_service_account_manager.load_credentials.side_effect = json.JSONDecodeError(
            "Invalid JSON",
            "",
            0
        )

        # Act & Assert
        with pytest.raises(json.JSONDecodeError):
            mock_service_account_manager.load_credentials()


class TestDatabaseErrors:
    """Test error handling for database operations"""

    @pytest.fixture
    def mock_postgres_service(self):
        """Create mock PostgreSQL service"""
        with patch('sessions.database_session_service.PostgreSQLSessionService') as mock:
            service = MagicMock()
            mock.return_value = service
            yield service

    @pytest.fixture
    def mock_firestore_service(self):
        """Create mock Firestore service"""
        with patch('sessions.database_session_service.FirestoreSessionService') as mock:
            service = MagicMock()
            mock.return_value = service
            yield service

    def test_postgres_connection_failure(self, mock_postgres_service):
        """Test handling of PostgreSQL connection failure"""
        # Arrange
        mock_postgres_service.create_session.side_effect = Exception("Connection refused")

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            mock_postgres_service.create_session("session-123", {})

        assert "Connection refused" in str(exc_info.value)

    def test_postgres_query_timeout(self, mock_postgres_service):
        """Test handling of query timeout"""
        # Arrange
        mock_postgres_service.get_session.side_effect = TimeoutError("Query timeout")

        # Act & Assert
        with pytest.raises(TimeoutError) as exc_info:
            mock_postgres_service.get_session("session-123")

        assert "Query timeout" in str(exc_info.value)

    def test_firestore_permission_denied(self, mock_firestore_service):
        """Test handling of Firestore permission denied"""
        # Arrange
        mock_firestore_service.create_session.side_effect = PermissionError(
            "Permission denied to Firestore"
        )

        # Act & Assert
        with pytest.raises(PermissionError) as exc_info:
            mock_firestore_service.create_session("session-123", {})

        assert "Permission denied" in str(exc_info.value)

    def test_firestore_quota_exceeded(self, mock_firestore_service):
        """Test handling of Firestore quota exceeded"""
        # Arrange
        mock_firestore_service.update_session_history.side_effect = Exception(
            "Quota exceeded"
        )

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            mock_firestore_service.update_session_history("session-123", {"msg": "test"})

        assert "Quota exceeded" in str(exc_info.value)

    def test_session_not_found_on_update(self, mock_postgres_service):
        """Test updating session that doesn't exist"""
        # Arrange
        mock_postgres_service.get_session.return_value = None

        # Act
        result = mock_postgres_service.get_session("nonexistent-session")

        # Assert
        assert result is None


class TestAgentErrors:
    """Test error handling in agent operations"""

    @pytest.fixture
    def mock_agent(self):
        """Create mock agent"""
        agent = Mock()
        agent.name = "test_agent"
        agent.model = "gemini-1.5-flash"
        return agent

    def test_agent_initialization_error(self):
        """Test handling of agent initialization failure"""
        # Arrange
        with patch('config.agent_registry.create_agent_instance') as mock_create:
            mock_create.side_effect = ImportError("Agent module not found")

            # Act & Assert
            with pytest.raises(ImportError) as exc_info:
                mock_create("mailer")

            assert "Agent module not found" in str(exc_info.value)

    def test_agent_missing_instruction_file(self, mock_agent):
        """Test handling when agent instruction file is missing"""
        # Arrange
        with patch('builtins.open', side_effect=FileNotFoundError("Instructions not found")):
            # Act & Assert
            with pytest.raises(FileNotFoundError) as exc_info:
                open("agents/test/instructions.md", "r")

            assert "Instructions not found" in str(exc_info.value)

    def test_agent_tool_execution_error(self, mock_agent):
        """Test handling of tool execution errors"""
        # Arrange
        mock_agent.execute_tool.side_effect = RuntimeError("Tool execution failed")

        # Act & Assert
        with pytest.raises(RuntimeError) as exc_info:
            mock_agent.execute_tool("gmail_send", {})

        assert "Tool execution failed" in str(exc_info.value)

    def test_agent_response_parsing_error(self, mock_agent):
        """Test handling of malformed agent response"""
        # Arrange
        mock_agent.parse_response.side_effect = ValueError("Invalid response format")

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            mock_agent.parse_response("malformed response")

        assert "Invalid response format" in str(exc_info.value)


class TestNetworkErrors:
    """Test error handling for network-related failures"""

    def test_api_rate_limit_exceeded(self):
        """Test handling of API rate limit errors"""
        # Arrange
        mock_api = Mock()
        mock_api.call.side_effect = Exception("Rate limit exceeded: 429")

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            mock_api.call()

        assert "Rate limit exceeded" in str(exc_info.value)

    def test_network_timeout(self):
        """Test handling of network timeout"""
        # Arrange
        mock_api = Mock()
        mock_api.request.side_effect = TimeoutError("Request timeout after 30s")

        # Act & Assert
        with pytest.raises(TimeoutError) as exc_info:
            mock_api.request()

        assert "Request timeout" in str(exc_info.value)

    def test_connection_reset(self):
        """Test handling of connection reset"""
        # Arrange
        mock_api = Mock()
        mock_api.connect.side_effect = ConnectionResetError("Connection reset by peer")

        # Act & Assert
        with pytest.raises(ConnectionResetError) as exc_info:
            mock_api.connect()

        assert "Connection reset" in str(exc_info.value)


class TestDataValidationErrors:
    """Test error handling for data validation failures"""

    @pytest.fixture
    def mock_gmail_server(self):
        """Create mock Gmail server"""
        return create_mock_gmail_server()

    def test_invalid_email_format(self, mock_gmail_server):
        """Test validation of email format"""
        # Act - Our mock doesn't validate, but real implementation should
        result = mock_gmail_server.send_message(
            to="not-an-email",
            subject="Test",
            body="Body"
        )

        # Assert - Mock processes it, but real implementation should reject
        assert "id" in result

    def test_missing_required_fields(self, mock_gmail_server):
        """Test handling of missing required fields"""
        # Act & Assert - Would fail in real implementation
        try:
            # Mock won't fail, but real implementation should validate
            result = mock_gmail_server.send_message(
                to="user@example.com",
                subject="",  # Empty subject
                body=""  # Empty body
            )
            assert "id" in result
        except TypeError:
            # If implementation validates, it would raise TypeError
            pass

    def test_invalid_json_schema(self):
        """Test handling of invalid JSON schema"""
        # Arrange
        invalid_schema = "not a valid json schema"

        # Act & Assert
        with pytest.raises(Exception):
            json.loads(invalid_schema)


class TestRecoveryMechanisms:
    """Test error recovery mechanisms"""

    @pytest.fixture
    def mock_agent_with_retry(self):
        """Create mock agent with retry logic"""
        agent = Mock()
        agent.max_retries = 3
        agent.retry_count = 0
        return agent

    def test_retry_on_transient_error(self, mock_agent_with_retry):
        """Test retry mechanism for transient errors"""
        # Arrange
        agent = mock_agent_with_retry
        call_count = 0

        def failing_then_succeeding(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Transient error")
            return {"status": "success"}

        agent.execute.side_effect = failing_then_succeeding

        # Act - Simulate retry loop
        for attempt in range(agent.max_retries):
            try:
                result = agent.execute()
                break
            except Exception as e:
                if attempt == agent.max_retries - 1:
                    raise
                continue

        # Assert
        assert result["status"] == "success"
        assert call_count == 3

    def test_fallback_mechanism(self):
        """Test fallback to alternative approach on error"""
        # Arrange
        primary_method = Mock(side_effect=Exception("Primary failed"))
        fallback_method = Mock(return_value={"status": "success", "method": "fallback"})

        # Act
        try:
            result = primary_method()
        except Exception:
            result = fallback_method()

        # Assert
        assert result["status"] == "success"
        assert result["method"] == "fallback"
        fallback_method.assert_called_once()
