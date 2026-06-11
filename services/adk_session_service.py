"""
Firestore-backed ADK Session Service
=====================================
Persists ADK session state (conversation history + tool context) to Firestore
so that agent context survives server restarts and session switches.

Feature flag: USE_PERSISTENT_ADK_SESSIONS=true  (default: false)
Collection:   adk_sessions/{session_id}

Design:
  - In-memory cache prevents Firestore reads on every event.
  - Writes are async (fire-and-forget from append_event, awaited on create).
  - Fallback: on any Firestore failure, session continues from in-memory cache.
"""

import os
import asyncio
import logging
import uuid
from typing import Optional, Any
from datetime import datetime, timezone

from google.adk.sessions import BaseSessionService, Session
from google.adk.sessions.base_session_service import ListSessionsResponse, GetSessionConfig
from google.adk.events import Event
from google.cloud.firestore_v1.async_client import AsyncClient

logger = logging.getLogger(__name__)

_COLLECTION = "adk_sessions"


class FirestoreADKSessionService(BaseSessionService):
    """
    ADK SessionService backed by Firestore.

    Stores full ADK Session (state + events) as serialized JSON.
    On create_session, checks Firestore first to restore existing sessions.
    On append_event, persists updated session asynchronously.

    Usage:
        service = FirestoreADKSessionService()
        runner = Runner(agent=agent, app_name="agents", session_service=service)
    """

    def __init__(self, project_id: Optional[str] = None):
        self._project_id = project_id or os.environ.get(
            'GOOGLE_CLOUD_PROJECT', 'lyrical-star-497817-m3'
        )
        self._db: Optional[AsyncClient] = None
        # In-memory cache: session_id -> Session
        self._cache: dict[str, Session] = {}

    def _get_db(self) -> AsyncClient:
        if self._db is None:
            self._db = AsyncClient(project=self._project_id)
            logger.info(f"[ADKSessionService] Firestore client initialized (project={self._project_id})")
        return self._db

    # ------------------------------------------------------------------
    # BaseSessionService interface
    # ------------------------------------------------------------------

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        """
        Get existing session from cache/Firestore, or create a new one.
        """
        if session_id is None:
            session_id = str(uuid.uuid4())

        # 1. Check in-memory cache first (cheapest)
        if session_id in self._cache:
            logger.debug(f"[ADKSessionService] Cache hit for '{session_id}'")
            return self._cache[session_id]

        # 2. Try to restore from Firestore
        restored = await self._load_from_firestore(session_id)
        if restored:
            self._cache[session_id] = restored
            logger.info(
                f"[ADKSessionService] Restored session '{session_id}' from Firestore "
                f"({len(restored.events)} events)"
            )
            return restored

        # 3. Create brand new session
        session = Session(
            id=session_id,
            app_name=app_name,
            user_id=user_id,
            state=state or {},
            events=[],
            last_update_time=0.0,
        )
        self._cache[session_id] = session
        # Persist immediately so session_id is "known" in Firestore
        await self._persist_to_firestore(session)
        logger.info(f"[ADKSessionService] Created new session '{session_id}'")
        return session

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: Optional[GetSessionConfig] = None,
    ) -> Optional[Session]:
        """Return session from cache or Firestore."""
        if session_id in self._cache:
            return self._cache[session_id]

        session = await self._load_from_firestore(session_id)
        if session:
            self._cache[session_id] = session
        return session

    async def list_sessions(
        self,
        *,
        app_name: str,
        user_id: Optional[str] = None,
    ) -> ListSessionsResponse:
        """Return cached sessions matching app_name / user_id."""
        sessions = [
            s for s in self._cache.values()
            if s.app_name == app_name and (user_id is None or s.user_id == user_id)
        ]
        return ListSessionsResponse(sessions=sessions)

    async def delete_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> None:
        """Remove session from cache and Firestore."""
        self._cache.pop(session_id, None)
        try:
            db = self._get_db()
            await db.collection(_COLLECTION).document(session_id).delete()
            logger.debug(f"[ADKSessionService] Deleted session '{session_id}'")
        except Exception as e:
            logger.error(f"[ADKSessionService] Failed to delete '{session_id}': {e}")

    async def append_event(self, session: Session, event: Event) -> Event:
        """
        Append event to session (in-memory) then persist async.
        Never blocks the caller — Firestore write is a background task.
        """
        event = await super().append_event(session, event)
        # Fire-and-forget: don't block streaming on Firestore write
        try:
            asyncio.get_running_loop().create_task(
                self._persist_to_firestore(session)
            )
        except RuntimeError:
            # No running loop (e.g., tests) — skip persistence
            pass
        return event

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _persist_to_firestore(self, session: Session) -> None:
        """Serialize and write session to Firestore."""
        try:
            db = self._get_db()
            data_json = session.model_dump_json()
            await db.collection(_COLLECTION).document(session.id).set({
                "session_id": session.id,
                "app_name": session.app_name,
                "user_id": session.user_id,
                "data": data_json,
                "event_count": len(session.events),
                "updated_at": datetime.now(timezone.utc),
            })
            logger.debug(
                f"[ADKSessionService] Persisted '{session.id}' "
                f"({len(session.events)} events)"
            )
        except Exception as e:
            logger.error(f"[ADKSessionService] Failed to persist '{session.id}': {e}")

    async def _load_from_firestore(self, session_id: str) -> Optional[Session]:
        """Load and deserialize session from Firestore. Returns None on miss/error."""
        try:
            db = self._get_db()
            doc = await db.collection(_COLLECTION).document(session_id).get()
            if doc.exists:
                data = doc.to_dict()
                if data and "data" in data:
                    session = Session.model_validate_json(data["data"])
                    return session
        except Exception as e:
            logger.error(f"[ADKSessionService] Failed to load '{session_id}': {e}")
        return None

    async def close(self) -> None:
        """Close Firestore client."""
        if self._db is not None:
            self._db.close()
            self._db = None
            logger.info("[ADKSessionService] Firestore client closed")
