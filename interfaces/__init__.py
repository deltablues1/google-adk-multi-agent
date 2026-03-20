"""
Interfaces Module

Provides different interface implementations for the Google Workspace ADK System.
Each interface (CLI, Telegram, Web, etc.) uses the same underlying agent system.
"""

from .base_interface import BaseInterface

# TelegramInterface is optional — only import if python-telegram-bot is installed.
# This prevents web/CLI startup from failing when the telegram package is not present.
try:
    from .telegram_interface import TelegramInterface
    __all__ = ['BaseInterface', 'TelegramInterface']
except ImportError:
    __all__ = ['BaseInterface']
