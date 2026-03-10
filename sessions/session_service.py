"""
Session Service

Wrapper oko DatabaseSessionService za perzistenciju stanja.
Trenutno koristi InMemorySessionService za development.
"""

from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class SessionService:
    """
    Session service za upravljanje stanjem između sesija

    U produkciji bi koristio DatabaseSessionService s PostgreSQL ili Firestore
    Za development koristi in-memory storage
    """

    def __init__(self, storage_type: str = "memory"):
        """
        Inicijalizacija session service-a

        Args:
            storage_type: Tip storage-a ("memory", "database", "firestore")
        """
        self.storage_type = storage_type
        self._sessions: Dict[str, Dict[str, Any]] = {}

        logger.info(f"SessionService initialized with storage: {storage_type}")

    def create_session(self, session_id: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Kreira novu sesiju

        Args:
            session_id: Jedinstveni ID sesije
            metadata: Dodatni metadata

        Returns:
            Session dictionary
        """
        session = {
            'session_id': session_id,
            'metadata': metadata or {},
            'history': [],
            'context': {}
        }

        self._sessions[session_id] = session
        logger.info(f"Created session: {session_id}")
        return session

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Dohvaća sesiju po ID-u

        Args:
            session_id: ID sesije

        Returns:
            Session dictionary ili None
        """
        return self._sessions.get(session_id)

    def update_session(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """
        Ažurira sesiju

        Args:
            session_id: ID sesije
            updates: Dictionary s ažuriranjima

        Returns:
            True ako je uspješno
        """
        if session_id not in self._sessions:
            logger.warning(f"Session not found: {session_id}")
            return False

        self._sessions[session_id].update(updates)
        logger.debug(f"Updated session: {session_id}")
        return True

    def delete_session(self, session_id: str) -> bool:
        """
        Briše sesiju

        Args:
            session_id: ID sesije

        Returns:
            True ako je uspješno
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"Deleted session: {session_id}")
            return True
        return False

    def add_message(self, session_id: str, message: Dict[str, Any]) -> bool:
        """
        Dodaje poruku u povijest sesije

        Args:
            session_id: ID sesije
            message: Message dictionary

        Returns:
            True ako je uspješno
        """
        session = self.get_session(session_id)
        if not session:
            return False

        session['history'].append(message)
        logger.debug(f"Added message to session {session_id}")
        return True

    def get_history(self, session_id: str, limit: Optional[int] = None) -> list:
        """
        Dohvaća povijest sesije

        Args:
            session_id: ID sesije
            limit: Maksimalan broj poruka (None = sve)

        Returns:
            Lista poruka
        """
        session = self.get_session(session_id)
        if not session:
            return []

        history = session.get('history', [])
        if limit:
            return history[-limit:]
        return history


# Singleton instance
_session_service: Optional[SessionService] = None


def get_session_service(storage_type: str = "memory") -> SessionService:
    """
    Dohvaća singleton instancu SessionService-a

    Args:
        storage_type: Tip storage-a

    Returns:
        SessionService instance
    """
    global _session_service
    if _session_service is None:
        _session_service = SessionService(storage_type=storage_type)
    return _session_service
