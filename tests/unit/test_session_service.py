"""
Unit tests for sessions.database_session_service.

Exercises the REAL implementations:
- PostgreSQLSessionService runs against a file-backed SQLite database through
  the same SQLAlchemy code path (engine/table/insert/select/update/delete).
- FirestoreSessionService runs against a mocked google.cloud.firestore.Client.
"""

import pytest
from unittest.mock import MagicMock, patch

from sessions.database_session_service import (
    DatabaseSessionServiceBase,
    PostgreSQLSessionService,
    FirestoreSessionService,
    create_database_session_service,
)


class TestDatabaseSessionServiceBase:
    """Interface contract of the abstract base class"""

    def test_base_class_is_abstract(self):
        with pytest.raises(TypeError):
            DatabaseSessionServiceBase()

    def test_interface_methods_defined(self):
        for method in ("create_session", "get_session", "update_session", "delete_session"):
            assert hasattr(DatabaseSessionServiceBase, method), \
                f"Base class should define {method}"


class TestPostgreSQLSessionService:
    """Real SQLAlchemy round-trips against SQLite (same code path as PostgreSQL)"""

    @pytest.fixture
    def service(self, tmp_path):
        return PostgreSQLSessionService(f"sqlite:///{tmp_path / 'sessions.db'}")

    def test_initialization_creates_table(self, service):
        assert service.engine is not None
        assert service.sessions_table is not None

    def test_create_and_get_session(self, service):
        created = service.create_session("session-123", {"user_id": "user-456"})
        assert created["session_id"] == "session-123"

        fetched = service.get_session("session-123")
        assert fetched is not None
        assert fetched["session_id"] == "session-123"
        assert fetched["metadata"] == {"user_id": "user-456"}
        assert fetched["history"] == []

    def test_get_session_not_exists(self, service):
        assert service.get_session("nonexistent") is None

    def test_update_session(self, service):
        service.create_session("session-123")
        ok = service.update_session(
            "session-123",
            {"history": [{"role": "user", "content": "Hello"}]},
        )
        assert ok is True
        assert service.get_session("session-123")["history"] == [
            {"role": "user", "content": "Hello"}
        ]

    def test_update_nonexistent_returns_false(self, service):
        assert service.update_session("nonexistent", {"history": []}) is False

    def test_delete_session(self, service):
        service.create_session("session-123")
        assert service.delete_session("session-123") is True
        assert service.get_session("session-123") is None

    def test_delete_nonexistent_returns_false(self, service):
        assert service.delete_session("nonexistent") is False


class TestFirestoreSessionService:
    """FirestoreSessionService with a mocked Firestore client"""

    @pytest.fixture
    def service_and_collection(self):
        with patch("google.cloud.firestore.Client") as MockClient:
            collection = MagicMock()
            MockClient.return_value.collection.return_value = collection
            service = FirestoreSessionService(project_id="test-project")
            yield service, collection

    def test_initialization(self, service_and_collection):
        service, _ = service_and_collection
        assert service.db is not None
        service.db  # collection 'adk_sessions' requested during init

    def test_create_session_sets_document(self, service_and_collection):
        service, collection = service_and_collection
        created = service.create_session("session-123", {"user_id": "user-456"})

        collection.document.assert_called_with("session-123")
        collection.document.return_value.set.assert_called_once()
        assert created["session_id"] == "session-123"
        assert created["metadata"] == {"user_id": "user-456"}

    def test_get_session_exists(self, service_and_collection):
        service, collection = service_and_collection
        doc = MagicMock()
        doc.exists = True
        doc.to_dict.return_value = {"session_id": "session-123", "history": []}
        collection.document.return_value.get.return_value = doc

        session = service.get_session("session-123")
        assert session == {"session_id": "session-123", "history": []}

    def test_get_session_not_exists(self, service_and_collection):
        service, collection = service_and_collection
        doc = MagicMock()
        doc.exists = False
        collection.document.return_value.get.return_value = doc

        assert service.get_session("nonexistent") is None

    def test_update_session(self, service_and_collection):
        service, collection = service_and_collection
        ok = service.update_session("session-123", {"history": [{"role": "user"}]})

        assert ok is True
        update_args = collection.document.return_value.update.call_args[0][0]
        assert "history" in update_args
        assert "updated_at" in update_args  # service stamps updated_at

    def test_update_session_error_returns_false(self, service_and_collection):
        service, collection = service_and_collection
        collection.document.return_value.update.side_effect = RuntimeError("boom")

        assert service.update_session("session-123", {"history": []}) is False

    def test_delete_session(self, service_and_collection):
        service, collection = service_and_collection
        assert service.delete_session("session-123") is True
        collection.document.return_value.delete.assert_called_once()


class TestFactory:
    """create_database_session_service factory"""

    def test_postgresql_requires_database_url(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(ValueError):
            create_database_session_service("postgresql")

    def test_postgresql_with_url(self, tmp_path):
        service = create_database_session_service(
            "postgresql", database_url=f"sqlite:///{tmp_path / 's.db'}"
        )
        assert isinstance(service, PostgreSQLSessionService)

    def test_firestore(self):
        with patch("google.cloud.firestore.Client"):
            service = create_database_session_service(
                "firestore", project_id="test-project"
            )
        assert isinstance(service, FirestoreSessionService)

    def test_unknown_storage_type_raises(self):
        with pytest.raises(ValueError):
            create_database_session_service("redis")
