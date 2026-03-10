"""
Session management module

Provides session persistence and state management
"""

from .session_service import SessionService, get_session_service

__all__ = [
    'SessionService',
    'get_session_service',
]
