"""
Database Session Service

Production-ready session persistence using PostgreSQL or Firestore
"""

import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class DatabaseSessionServiceBase(ABC):
    """Base class for database session services"""

    @abstractmethod
    def create_session(self, session_id: str, metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """Create new session"""
        pass

    @abstractmethod
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session by ID"""
        pass

    @abstractmethod
    def update_session(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """Update session"""
        pass

    @abstractmethod
    def delete_session(self, session_id: str) -> bool:
        """Delete session"""
        pass


# ============================================================================
# PostgreSQL Implementation
# ============================================================================

class PostgreSQLSessionService(DatabaseSessionServiceBase):
    """PostgreSQL session service implementation"""

    def __init__(self, database_url: str):
        """
        Initialize PostgreSQL session service

        Args:
            database_url: PostgreSQL connection string
        """
        self.database_url = database_url
        self._engine = None
        self._init_database()

    def _init_database(self):
        """Initialize database connection and create tables"""
        try:
            from sqlalchemy import create_engine, Table, Column, String, JSON, DateTime, MetaData
            from sqlalchemy.pool import QueuePool

            # Create engine with connection pooling
            self.engine = create_engine(
                self.database_url,
                poolclass=QueuePool,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
                echo=False
            )

            # Define schema
            self.metadata = MetaData()
            self.sessions_table = Table(
                'adk_sessions',
                self.metadata,
                Column('session_id', String, primary_key=True),
                Column('metadata', JSON),
                Column('history', JSON),
                Column('context', JSON),
                Column('created_at', DateTime, default=datetime.utcnow),
                Column('updated_at', DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
            )

            # Create tables
            self.metadata.create_all(self.engine)
            logger.info("PostgreSQL session service initialized")

        except ImportError:
            logger.error("SQLAlchemy not installed. Install with: pip install sqlalchemy psycopg2-binary")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL: {e}")
            raise

    def create_session(self, session_id: str, metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """Create new session in PostgreSQL"""
        from sqlalchemy import insert

        session_data = {
            'session_id': session_id,
            'metadata': metadata or {},
            'history': [],
            'context': {},
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }

        try:
            with self.engine.connect() as conn:
                conn.execute(insert(self.sessions_table).values(**session_data))
                conn.commit()
            logger.info(f"Created session: {session_id}")
            return session_data
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            raise

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session from PostgreSQL"""
        from sqlalchemy import select

        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    select(self.sessions_table).where(
                        self.sessions_table.c.session_id == session_id
                    )
                ).fetchone()

                if result:
                    return dict(result._mapping)
                return None
        except Exception as e:
            logger.error(f"Failed to get session: {e}")
            return None

    def update_session(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """Update session in PostgreSQL"""
        from sqlalchemy import update

        updates['updated_at'] = datetime.utcnow()

        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    update(self.sessions_table).where(
                        self.sessions_table.c.session_id == session_id
                    ).values(**updates)
                )
                conn.commit()
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update session: {e}")
            return False

    def delete_session(self, session_id: str) -> bool:
        """Delete session from PostgreSQL"""
        from sqlalchemy import delete

        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    delete(self.sessions_table).where(
                        self.sessions_table.c.session_id == session_id
                    )
                )
                conn.commit()
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete session: {e}")
            return False


# ============================================================================
# Firestore Implementation
# ============================================================================

class FirestoreSessionService(DatabaseSessionServiceBase):
    """Firestore session service implementation"""

    def __init__(self, project_id: Optional[str] = None):
        """
        Initialize Firestore session service

        Args:
            project_id: Google Cloud project ID
        """
        self.project_id = project_id
        self._init_firestore()

    def _init_firestore(self):
        """Initialize Firestore client"""
        try:
            from google.cloud import firestore

            self.db = firestore.Client(project=self.project_id)
            self.collection = self.db.collection('adk_sessions')
            logger.info("Firestore session service initialized")

        except ImportError:
            logger.error("Firestore not installed. Install with: pip install google-cloud-firestore")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize Firestore: {e}")
            raise

    def create_session(self, session_id: str, metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """Create new session in Firestore"""
        from google.cloud import firestore

        session_data = {
            'session_id': session_id,
            'metadata': metadata or {},
            'history': [],
            'context': {},
            'created_at': firestore.SERVER_TIMESTAMP,
            'updated_at': firestore.SERVER_TIMESTAMP
        }

        try:
            self.collection.document(session_id).set(session_data)
            logger.info(f"Created session: {session_id}")
            return session_data
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            raise

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session from Firestore"""
        try:
            doc = self.collection.document(session_id).get()
            if doc.exists:
                return doc.to_dict()
            return None
        except Exception as e:
            logger.error(f"Failed to get session: {e}")
            return None

    def update_session(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """Update session in Firestore"""
        from google.cloud import firestore

        updates['updated_at'] = firestore.SERVER_TIMESTAMP

        try:
            self.collection.document(session_id).update(updates)
            return True
        except Exception as e:
            logger.error(f"Failed to update session: {e}")
            return False

    def delete_session(self, session_id: str) -> bool:
        """Delete session from Firestore"""
        try:
            self.collection.document(session_id).delete()
            return True
        except Exception as e:
            logger.error(f"Failed to delete session: {e}")
            return False


# ============================================================================
# Factory Function
# ============================================================================

def create_database_session_service(
    storage_type: str = "postgresql",
    **kwargs
) -> DatabaseSessionServiceBase:
    """
    Factory function for creating database session service

    Args:
        storage_type: Type of storage ("postgresql" or "firestore")
        **kwargs: Additional arguments for specific implementation

    Returns:
        DatabaseSessionServiceBase instance
    """
    if storage_type == "postgresql":
        database_url = kwargs.get('database_url') or os.environ.get('DATABASE_URL')
        if not database_url:
            raise ValueError("database_url required for PostgreSQL")
        return PostgreSQLSessionService(database_url)

    elif storage_type == "firestore":
        project_id = kwargs.get('project_id') or os.environ.get('GOOGLE_CLOUD_PROJECT')
        return FirestoreSessionService(project_id)

    else:
        raise ValueError(f"Unknown storage type: {storage_type}")


import os
