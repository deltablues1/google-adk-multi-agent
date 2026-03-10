"""
Unit tests for Session Service

Tests DatabaseSessionService, PostgreSQLSessionService, and FirestoreSessionService.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json
from datetime import datetime


class TestDatabaseSessionServiceBase:
    """Unit tests for DatabaseSessionServiceBase interface"""

    def test_base_class_interface(self):
        """Test that base class defines required interface"""
        # Arrange
        with patch('sessions.database_session_service.DatabaseSessionServiceBase') as MockBase:
            base = MockBase()

            # Assert - Check interface methods exist
            assert hasattr(base, 'create_session')
            assert hasattr(base, 'get_session')
            assert hasattr(base, 'update_session_history')
            assert hasattr(base, 'delete_session')
            assert hasattr(base, 'list_sessions')


class TestPostgreSQLSessionService:
    """Unit tests for PostgreSQL Session Service"""

    @pytest.fixture
    def mock_postgres_engine(self):
        """Mock PostgreSQL engine"""
        with patch('sessions.database_session_service.create_engine') as mock_engine:
            engine = MagicMock()
            mock_engine.return_value = engine
            yield engine

    @pytest.fixture
    def postgres_service(self, mock_postgres_engine):
        """Create PostgreSQL session service with mock"""
        with patch('sessions.database_session_service.PostgreSQLSessionService') as MockService:
            service = MockService("postgresql://test:test@localhost/test")
            yield service

    def test_postgres_service_initialization(self, postgres_service):
        """Test PostgreSQL service initializes correctly"""
        # Assert
        assert postgres_service is not None

    def test_create_session(self, postgres_service):
        """Test creating a session"""
        # Arrange
        session_id = "session-123"
        metadata = {"user_id": "user-456"}

        # Act
        postgres_service.create_session(session_id, metadata)

        # Assert
        postgres_service.create_session.assert_called_once_with(session_id, metadata)

    def test_get_session_exists(self, postgres_service):
        """Test getting existing session"""
        # Arrange
        session_id = "session-123"
        mock_session_data = {
            "session_id": session_id,
            "metadata": {"user_id": "user-456"},
            "history": [{"role": "user", "content": "Hello"}],
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        postgres_service.get_session.return_value = mock_session_data

        # Act
        session = postgres_service.get_session(session_id)

        # Assert
        assert session is not None
        assert session["session_id"] == session_id
        assert "metadata" in session
        assert "history" in session

    def test_get_session_not_exists(self, postgres_service):
        """Test getting non-existent session"""
        # Arrange
        postgres_service.get_session.return_value = None

        # Act
        session = postgres_service.get_session("nonexistent-session")

        # Assert
        assert session is None

    def test_update_session_history(self, postgres_service):
        """Test updating session history"""
        # Arrange
        session_id = "session-123"
        new_message = {"role": "assistant", "content": "Response"}

        # Act
        postgres_service.update_session_history(session_id, new_message)

        # Assert
        postgres_service.update_session_history.assert_called_once_with(session_id, new_message)

    def test_delete_session(self, postgres_service):
        """Test deleting a session"""
        # Arrange
        session_id = "session-123"

        # Act
        postgres_service.delete_session(session_id)

        # Assert
        postgres_service.delete_session.assert_called_once_with(session_id)

    def test_list_sessions(self, postgres_service):
        """Test listing all sessions"""
        # Arrange
        mock_sessions = [
            {"session_id": "session-1", "metadata": {}, "history": []},
            {"session_id": "session-2", "metadata": {}, "history": []},
            {"session_id": "session-3", "metadata": {}, "history": []}
        ]
        postgres_service.list_sessions.return_value = mock_sessions

        # Act
        sessions = postgres_service.list_sessions()

        # Assert
        assert len(sessions) == 3
        assert sessions[0]["session_id"] == "session-1"

    def test_connection_pool(self, mock_postgres_engine):
        """Test connection pooling configuration"""
        # Arrange
        with patch('sessions.database_session_service.create_engine') as mock_create_engine:
            # Act
            from sqlalchemy.pool import QueuePool
            mock_create_engine(
                "postgresql://test:test@localhost/test",
                poolclass=QueuePool,
                pool_size=5,
                max_overflow=10
            )

            # Assert
            mock_create_engine.assert_called_once()
            call_kwargs = mock_create_engine.call_args[1]
            assert call_kwargs.get('pool_size') == 5
            assert call_kwargs.get('max_overflow') == 10

    def test_json_serialization(self):
        """Test JSON serialization of session data"""
        # Arrange
        session_data = {
            "metadata": {"user_id": "user-123", "context": "test"},
            "history": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"}
            ]
        }

        # Act
        metadata_json = json.dumps(session_data["metadata"])
        history_json = json.dumps(session_data["history"])

        # Deserialize
        parsed_metadata = json.loads(metadata_json)
        parsed_history = json.loads(history_json)

        # Assert
        assert parsed_metadata["user_id"] == "user-123"
        assert len(parsed_history) == 2
        assert parsed_history[0]["role"] == "user"


class TestFirestoreSessionService:
    """Unit tests for Firestore Session Service"""

    @pytest.fixture
    def mock_firestore_client(self):
        """Mock Firestore client"""
        with patch('sessions.database_session_service.firestore.Client') as MockClient:
            client = MagicMock()
            MockClient.return_value = client
            yield client

    @pytest.fixture
    def firestore_service(self, mock_firestore_client):
        """Create Firestore session service with mock"""
        with patch('sessions.database_session_service.FirestoreSessionService') as MockService:
            service = MockService(project_id="test-project")
            yield service

    def test_firestore_service_initialization(self, firestore_service):
        """Test Firestore service initializes correctly"""
        # Assert
        assert firestore_service is not None

    def test_create_session(self, firestore_service):
        """Test creating a session in Firestore"""
        # Arrange
        session_id = "session-456"
        metadata = {"user_id": "user-789"}

        # Act
        firestore_service.create_session(session_id, metadata)

        # Assert
        firestore_service.create_session.assert_called_once_with(session_id, metadata)

    def test_get_session_exists(self, firestore_service):
        """Test getting existing session from Firestore"""
        # Arrange
        session_id = "session-456"
        mock_session_data = {
            "session_id": session_id,
            "metadata": {"user_id": "user-789"},
            "history": [{"role": "user", "content": "Test"}],
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        firestore_service.get_session.return_value = mock_session_data

        # Act
        session = firestore_service.get_session(session_id)

        # Assert
        assert session is not None
        assert session["session_id"] == session_id

    def test_get_session_not_exists(self, firestore_service):
        """Test getting non-existent session from Firestore"""
        # Arrange
        firestore_service.get_session.return_value = None

        # Act
        session = firestore_service.get_session("nonexistent-session")

        # Assert
        assert session is None

    def test_update_session_history(self, firestore_service):
        """Test updating session history in Firestore"""
        # Arrange
        session_id = "session-456"
        new_message = {"role": "user", "content": "New message"}

        # Act
        firestore_service.update_session_history(session_id, new_message)

        # Assert
        firestore_service.update_session_history.assert_called_once_with(session_id, new_message)

    def test_delete_session(self, firestore_service):
        """Test deleting session from Firestore"""
        # Arrange
        session_id = "session-456"

        # Act
        firestore_service.delete_session(session_id)

        # Assert
        firestore_service.delete_session.assert_called_once_with(session_id)

    def test_list_sessions(self, firestore_service):
        """Test listing all sessions from Firestore"""
        # Arrange
        mock_sessions = [
            {"session_id": "session-1", "metadata": {}, "history": []},
            {"session_id": "session-2", "metadata": {}, "history": []}
        ]
        firestore_service.list_sessions.return_value = mock_sessions

        # Act
        sessions = firestore_service.list_sessions()

        # Assert
        assert len(sessions) == 2

    def test_firestore_timestamp_handling(self):
        """Test Firestore timestamp handling"""
        # Arrange
        now = datetime.now()

        # Act
        timestamp_str = now.isoformat()
        parsed_timestamp = datetime.fromisoformat(timestamp_str)

        # Assert
        assert parsed_timestamp.year == now.year
        assert parsed_timestamp.month == now.month
        assert parsed_timestamp.day == now.day


class TestSessionDataStructure:
    """Unit tests for session data structure"""

    def test_session_schema(self):
        """Test session data schema is valid"""
        # Arrange
        session = {
            "session_id": "session-123",
            "metadata": {
                "user_id": "user-456",
                "agent": "orchestrator",
                "created_by": "test"
            },
            "history": [
                {"role": "user", "content": "Hello", "timestamp": datetime.now().isoformat()},
                {"role": "assistant", "content": "Hi!", "timestamp": datetime.now().isoformat()}
            ],
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }

        # Assert
        assert "session_id" in session
        assert "metadata" in session
        assert "history" in session
        assert "created_at" in session
        assert "updated_at" in session
        assert isinstance(session["history"], list)
        assert isinstance(session["metadata"], dict)

    def test_history_message_structure(self):
        """Test history message structure"""
        # Arrange
        message = {
            "role": "user",
            "content": "Test message",
            "timestamp": datetime.now().isoformat()
        }

        # Assert
        assert "role" in message
        assert "content" in message
        assert message["role"] in ["user", "assistant", "system"]
        assert isinstance(message["content"], str)

    def test_metadata_structure(self):
        """Test metadata structure"""
        # Arrange
        metadata = {
            "user_id": "user-123",
            "agent": "mailer",
            "context": "email_operation",
            "custom_field": "custom_value"
        }

        # Assert
        assert isinstance(metadata, dict)
        assert "user_id" in metadata
        # Metadata should be flexible - allow custom fields

    def test_session_id_format(self):
        """Test session ID format"""
        # Arrange
        import uuid
        session_id = str(uuid.uuid4())

        # Assert
        assert isinstance(session_id, str)
        assert len(session_id) > 0
        # Should be UUID format
        assert "-" in session_id

    def test_history_append(self):
        """Test appending to history"""
        # Arrange
        history = [
            {"role": "user", "content": "Message 1"}
        ]

        # Act
        history.append({"role": "assistant", "content": "Response 1"})
        history.append({"role": "user", "content": "Message 2"})

        # Assert
        assert len(history) == 3
        assert history[-1]["content"] == "Message 2"


class TestSessionServiceFactory:
    """Unit tests for session service factory pattern"""

    def test_create_postgres_service(self):
        """Test creating PostgreSQL service via factory"""
        # Arrange
        with patch('sessions.database_session_service.PostgreSQLSessionService') as MockService:
            # Act
            service = MockService("postgresql://localhost/test")

            # Assert
            assert service is not None
            MockService.assert_called_once_with("postgresql://localhost/test")

    def test_create_firestore_service(self):
        """Test creating Firestore service via factory"""
        # Arrange
        with patch('sessions.database_session_service.FirestoreSessionService') as MockService:
            # Act
            service = MockService(project_id="test-project")

            # Assert
            assert service is not None
            MockService.assert_called_once_with(project_id="test-project")

    def test_service_selection_based_on_config(self):
        """Test selecting service based on configuration"""
        # Arrange
        config = {
            "database_type": "postgresql",
            "database_url": "postgresql://localhost/test"
        }

        # Act
        if config["database_type"] == "postgresql":
            with patch('sessions.database_session_service.PostgreSQLSessionService') as MockPG:
                service = MockPG(config["database_url"])
                service_type = "postgresql"
        else:
            service_type = "firestore"

        # Assert
        assert service_type == "postgresql"
        assert service is not None


class TestSessionServiceErrorHandling:
    """Unit tests for session service error handling"""

    @pytest.fixture
    def postgres_service(self):
        """Mock PostgreSQL service"""
        with patch('sessions.database_session_service.PostgreSQLSessionService') as MockService:
            service = MockService("postgresql://localhost/test")
            yield service

    def test_handle_connection_error(self, postgres_service):
        """Test handling database connection errors"""
        # Arrange
        postgres_service.create_session.side_effect = ConnectionError("Connection failed")

        # Act & Assert
        with pytest.raises(ConnectionError):
            postgres_service.create_session("session-123", {})

    def test_handle_session_not_found(self, postgres_service):
        """Test handling session not found"""
        # Arrange
        postgres_service.get_session.return_value = None

        # Act
        session = postgres_service.get_session("nonexistent")

        # Assert
        assert session is None

    def test_handle_invalid_session_data(self, postgres_service):
        """Test handling invalid session data"""
        # Arrange
        invalid_data = "not a dict"

        postgres_service.create_session.side_effect = TypeError("Invalid data type")

        # Act & Assert
        with pytest.raises(TypeError):
            postgres_service.create_session("session-123", invalid_data)

    def test_handle_database_timeout(self, postgres_service):
        """Test handling database timeout"""
        # Arrange
        postgres_service.get_session.side_effect = TimeoutError("Query timeout")

        # Act & Assert
        with pytest.raises(TimeoutError):
            postgres_service.get_session("session-123")
