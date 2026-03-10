"""
Integration tests for Database Session Service

Tests the full session lifecycle with both PostgreSQL and Firestore backends.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any
import json
from datetime import datetime

from sessions.database_session_service import (
    DatabaseSessionServiceBase,
    PostgreSQLSessionService,
    FirestoreSessionService
)


class TestPostgreSQLSessionFlow:
    """Test PostgreSQL session service integration"""

    @pytest.fixture
    def mock_postgres_engine(self):
        """Create mock SQLAlchemy engine"""
        with patch('sessions.database_session_service.create_engine') as mock_engine:
            # Mock connection and cursor
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_engine.return_value.raw_connection.return_value = mock_conn

            # Mock execute results
            mock_cursor.fetchone.return_value = None
            mock_cursor.fetchall.return_value = []

            yield mock_engine

    @pytest.fixture
    def postgres_service(self, mock_postgres_engine):
        """Create PostgreSQL session service with mock"""
        service = PostgreSQLSessionService(database_url="postgresql://test:test@localhost/test_db")
        return service

    def test_create_session(self, postgres_service):
        """Test creating a new session"""
        # Arrange
        session_id = "test-session-123"
        metadata = {"user_id": "user-456", "agent": "orchestrator"}

        # Act
        with patch.object(postgres_service.engine, 'raw_connection') as mock_conn_method:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_conn_method.return_value = mock_conn

            postgres_service.create_session(session_id, metadata)

            # Assert
            mock_cursor.execute.assert_called()
            args = mock_cursor.execute.call_args[0]
            assert "INSERT INTO adk_sessions" in args[0]
            assert session_id in args[1]

    def test_get_session(self, postgres_service):
        """Test retrieving session"""
        # Arrange
        session_id = "test-session-123"
        mock_session_data = {
            "session_id": session_id,
            "metadata": json.dumps({"user_id": "user-456"}),
            "history": json.dumps([{"role": "user", "content": "Hello"}]),
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }

        # Act
        with patch.object(postgres_service.engine, 'raw_connection') as mock_conn_method:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_conn_method.return_value = mock_conn

            # Mock the fetchone to return session data
            mock_cursor.fetchone.return_value = (
                session_id,
                mock_session_data["metadata"],
                mock_session_data["history"],
                mock_session_data["created_at"],
                mock_session_data["updated_at"]
            )

            session = postgres_service.get_session(session_id)

            # Assert
            assert session is not None
            assert session["session_id"] == session_id
            assert "metadata" in session
            assert "history" in session

    def test_update_session_history(self, postgres_service):
        """Test updating session history"""
        # Arrange
        session_id = "test-session-123"
        new_message = {"role": "assistant", "content": "Hello! How can I help?"}

        # Act
        with patch.object(postgres_service.engine, 'raw_connection') as mock_conn_method:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_conn_method.return_value = mock_conn

            # Mock existing session
            mock_cursor.fetchone.return_value = (
                session_id,
                json.dumps({}),
                json.dumps([{"role": "user", "content": "Hello"}]),
                datetime.now(),
                datetime.now()
            )

            postgres_service.update_session_history(session_id, new_message)

            # Assert - check UPDATE was called
            update_called = any(
                "UPDATE adk_sessions" in str(call)
                for call in mock_cursor.execute.call_args_list
            )
            assert update_called

    def test_delete_session(self, postgres_service):
        """Test deleting a session"""
        # Arrange
        session_id = "test-session-123"

        # Act
        with patch.object(postgres_service.engine, 'raw_connection') as mock_conn_method:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_conn_method.return_value = mock_conn

            postgres_service.delete_session(session_id)

            # Assert
            args = mock_cursor.execute.call_args[0]
            assert "DELETE FROM adk_sessions" in args[0]
            assert session_id in args[1]

    def test_list_sessions(self, postgres_service):
        """Test listing all sessions"""
        # Arrange
        mock_sessions = [
            ("session-1", json.dumps({}), json.dumps([]), datetime.now(), datetime.now()),
            ("session-2", json.dumps({}), json.dumps([]), datetime.now(), datetime.now()),
            ("session-3", json.dumps({}), json.dumps([]), datetime.now(), datetime.now())
        ]

        # Act
        with patch.object(postgres_service.engine, 'raw_connection') as mock_conn_method:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_conn_method.return_value = mock_conn

            mock_cursor.fetchall.return_value = mock_sessions

            sessions = postgres_service.list_sessions()

            # Assert
            assert isinstance(sessions, list)
            assert len(sessions) == 3


class TestFirestoreSessionFlow:
    """Test Firestore session service integration"""

    @pytest.fixture
    def mock_firestore_client(self):
        """Create mock Firestore client"""
        with patch('sessions.database_session_service.firestore.Client') as mock_client:
            mock_db = MagicMock()
            mock_collection = MagicMock()
            mock_db.collection.return_value = mock_collection
            mock_client.return_value = mock_db
            yield mock_client

    @pytest.fixture
    def firestore_service(self, mock_firestore_client):
        """Create Firestore session service with mock"""
        service = FirestoreSessionService(project_id="test-project")
        return service

    def test_create_session(self, firestore_service):
        """Test creating a new session in Firestore"""
        # Arrange
        session_id = "test-session-456"
        metadata = {"user_id": "user-789", "agent": "mailer"}

        # Act
        with patch.object(firestore_service.collection, 'document') as mock_doc:
            mock_doc_ref = MagicMock()
            mock_doc.return_value = mock_doc_ref

            firestore_service.create_session(session_id, metadata)

            # Assert
            mock_doc.assert_called_with(session_id)
            mock_doc_ref.set.assert_called_once()

    def test_get_session(self, firestore_service):
        """Test retrieving session from Firestore"""
        # Arrange
        session_id = "test-session-456"
        mock_data = {
            "session_id": session_id,
            "metadata": {"user_id": "user-789"},
            "history": [{"role": "user", "content": "Test"}],
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }

        # Act
        with patch.object(firestore_service.collection, 'document') as mock_doc:
            mock_doc_ref = MagicMock()
            mock_snapshot = MagicMock()
            mock_snapshot.exists = True
            mock_snapshot.to_dict.return_value = mock_data
            mock_doc_ref.get.return_value = mock_snapshot
            mock_doc.return_value = mock_doc_ref

            session = firestore_service.get_session(session_id)

            # Assert
            assert session is not None
            assert session["session_id"] == session_id
            assert session["metadata"]["user_id"] == "user-789"

    def test_get_nonexistent_session(self, firestore_service):
        """Test getting session that doesn't exist"""
        # Arrange
        session_id = "nonexistent-session"

        # Act
        with patch.object(firestore_service.collection, 'document') as mock_doc:
            mock_doc_ref = MagicMock()
            mock_snapshot = MagicMock()
            mock_snapshot.exists = False
            mock_doc_ref.get.return_value = mock_snapshot
            mock_doc.return_value = mock_doc_ref

            session = firestore_service.get_session(session_id)

            # Assert
            assert session is None

    def test_update_session_history(self, firestore_service):
        """Test updating session history in Firestore"""
        # Arrange
        session_id = "test-session-456"
        new_message = {"role": "assistant", "content": "Response"}
        existing_history = [{"role": "user", "content": "Question"}]

        # Act
        with patch.object(firestore_service.collection, 'document') as mock_doc:
            mock_doc_ref = MagicMock()
            mock_snapshot = MagicMock()
            mock_snapshot.exists = True
            mock_snapshot.to_dict.return_value = {
                "session_id": session_id,
                "history": existing_history,
                "metadata": {}
            }
            mock_doc_ref.get.return_value = mock_snapshot
            mock_doc.return_value = mock_doc_ref

            firestore_service.update_session_history(session_id, new_message)

            # Assert
            mock_doc_ref.update.assert_called_once()
            update_data = mock_doc_ref.update.call_args[0][0]
            assert "history" in update_data
            assert len(update_data["history"]) == 2

    def test_delete_session(self, firestore_service):
        """Test deleting session from Firestore"""
        # Arrange
        session_id = "test-session-456"

        # Act
        with patch.object(firestore_service.collection, 'document') as mock_doc:
            mock_doc_ref = MagicMock()
            mock_doc.return_value = mock_doc_ref

            firestore_service.delete_session(session_id)

            # Assert
            mock_doc.assert_called_with(session_id)
            mock_doc_ref.delete.assert_called_once()

    def test_list_sessions(self, firestore_service):
        """Test listing all sessions from Firestore"""
        # Arrange
        mock_sessions = [
            MagicMock(to_dict=lambda: {"session_id": "session-1", "metadata": {}, "history": []}),
            MagicMock(to_dict=lambda: {"session_id": "session-2", "metadata": {}, "history": []}),
        ]

        # Act
        with patch.object(firestore_service.collection, 'stream') as mock_stream:
            mock_stream.return_value = mock_sessions

            sessions = firestore_service.list_sessions()

            # Assert
            assert isinstance(sessions, list)
            assert len(sessions) == 2


class TestSessionLifecycle:
    """Test complete session lifecycle"""

    @pytest.fixture
    def session_service(self):
        """Create mock session service"""
        with patch('sessions.database_session_service.create_engine'):
            service = PostgreSQLSessionService(database_url="postgresql://test:test@localhost/test")
            return service

    def test_full_session_lifecycle(self, session_service):
        """Test create -> update -> retrieve -> delete flow"""
        # Arrange
        session_id = "lifecycle-test-session"
        metadata = {"user_id": "user-123", "context": "testing"}

        with patch.object(session_service.engine, 'raw_connection') as mock_conn_method:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_conn_method.return_value = mock_conn

            # Step 1: Create
            session_service.create_session(session_id, metadata)
            assert mock_cursor.execute.called

            # Step 2: Update
            mock_cursor.fetchone.return_value = (
                session_id,
                json.dumps(metadata),
                json.dumps([]),
                datetime.now(),
                datetime.now()
            )
            session_service.update_session_history(session_id, {"role": "user", "content": "Hi"})

            # Step 3: Retrieve
            session = session_service.get_session(session_id)
            assert session is not None

            # Step 4: Delete
            session_service.delete_session(session_id)

            # Verify all operations were called
            assert mock_cursor.execute.call_count >= 4  # Create, Get, Update, Delete

    def test_session_history_accumulation(self, session_service):
        """Test that session history accumulates correctly"""
        # Arrange
        session_id = "history-test-session"
        messages = [
            {"role": "user", "content": "Message 1"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "Message 2"},
            {"role": "assistant", "content": "Response 2"}
        ]

        with patch.object(session_service.engine, 'raw_connection') as mock_conn_method:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_conn_method.return_value = mock_conn

            # Create session
            session_service.create_session(session_id, {})

            # Add messages one by one
            current_history = []
            for msg in messages:
                current_history.append(msg)
                mock_cursor.fetchone.return_value = (
                    session_id,
                    json.dumps({}),
                    json.dumps(current_history[:-1]),  # History before this update
                    datetime.now(),
                    datetime.now()
                )
                session_service.update_session_history(session_id, msg)

            # Verify multiple updates occurred
            assert mock_cursor.execute.call_count >= len(messages)
