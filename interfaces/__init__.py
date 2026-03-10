"""
Interfaces Module

Provides different interface implementations for the Google Workspace ADK System.
Each interface (CLI, Telegram, Web, etc.) uses the same underlying agent system.
"""

from .base_interface import BaseInterface
from .telegram_interface import TelegramInterface

__all__ = ['BaseInterface', 'TelegramInterface']
