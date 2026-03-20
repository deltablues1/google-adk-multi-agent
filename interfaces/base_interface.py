"""
Base Interface for Google Workspace ADK System

Abstract base class that defines the interface contract for different
communication channels (CLI, Telegram, Web API, etc.)
"""

import os
import logging
import time
import uuid
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)


class BaseInterface(ABC):
    """
    Abstract base class for all interface implementations.

    All interfaces share the same WorkspaceADKSystem but differ in how they:
    - Receive user input
    - Send responses
    - Handle sessions
    - Format output
    """

    def __init__(self, session_prefix: str = "interface"):
        """
        Initialize base interface.

        Args:
            session_prefix: Prefix for session IDs (e.g., 'cli', 'telegram', 'web')
        """
        self.session_prefix = session_prefix
        self.system = None
        self.active_sessions: Dict[str, Any] = {}

        # Lazy import to avoid circular dependencies
        self._system_class = None

    def _get_system_class(self):
        """Lazy load WorkspaceADKSystem to avoid import issues."""
        if self._system_class is None:
            # Import here to avoid circular imports
            from main import WorkspaceADKSystem
            self._system_class = WorkspaceADKSystem
        return self._system_class

    def generate_session_id(self, user_id: str) -> str:
        """
        Generate a unique session ID for a user.

        Args:
            user_id: Unique identifier for the user

        Returns:
            Session ID string
        """
        return f"{self.session_prefix}-{user_id}-{uuid.uuid4().hex[:8]}"

    def initialize_system(self) -> None:
        """
        Initialize the WorkspaceADKSystem.

        This creates and configures the agent system.
        """
        logger.info(f"Initializing system for {self.session_prefix} interface...")

        SystemClass = self._get_system_class()
        self.system = SystemClass()
        self.system.initialize_agents()

        logger.info(f"System initialized for {self.session_prefix} interface")

    async def process_message(
        self,
        user_id: str,
        message: str,
        session_id: Optional[str] = None
    ) -> str:
        """
        Process a user message through the agent system.

        Args:
            user_id: Unique identifier for the user
            message: The user's message text
            session_id: Optional existing session ID

        Returns:
            Agent response string
        """
        if self.system is None:
            self.initialize_system()

        # Get or create session
        if session_id is None:
            session_id = self.generate_session_id(user_id)

        # Update system session
        self.system.session_id = session_id
        self.system.user_id = user_id

        # CRITICAL: Recreate RunnerHelper with correct session for this interface
        # The original RunnerHelper was created with CLI session, we need one for Telegram
        if self.system.orchestrator_helper:
            current_helper_session = self.system.orchestrator_helper.session_id
            if current_helper_session != session_id:
                logger.info(f"Creating new RunnerHelper for session '{session_id}' (was '{current_helper_session}')")
                from agents.adk_agents.runner_utils import RunnerHelper
                # Reuse existing session_service from current helper so ADK context is shared
                existing_service = getattr(self.system.orchestrator_helper, 'session_service', None)
                self.system.orchestrator_helper = RunnerHelper(
                    agent=self.system.orchestrator,
                    session_id=session_id,
                    user_id=user_id,
                    app_name="agents",
                    session_service=existing_service,
                )

        try:
            # Check for mode routing (CLASSROOM vs LEGACY)
            if self.system.active_mode == "CLASSROOM":
                result = await self._process_classroom_mode(message)
            else:
                # Check if we should switch to CLASSROOM using keyword-based routing
                # (master_router replaced with inline keyword check - same logic as CLI)
                msg_lower = message.lower()
                if any(kw in msg_lower for kw in self.system.philosophy_keywords):
                    self.system.active_mode = "CLASSROOM"
                    result = await self._process_classroom_mode(message, first_entry=True)
                else:
                    # Use Smart Orchestrator
                    result = await self.system.orchestrator_helper.run(message)

            return result

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return f"Error processing request: {str(e)}"

    async def _process_classroom_mode(self, message: str, first_entry: bool = False) -> str:
        """
        Process message in Philosophy Classroom mode.

        Args:
            message: User message
            first_entry: Whether this is first entry to classroom

        Returns:
            Socrates response
        """
        prefix = "Entering Philosophy Classroom...\n\n" if first_entry else ""

        # Run Socrates
        socrates_response = await self.system.socrates.run_with_fallback(message)

        # Check for termination
        check_input = f"User input: {message}\nSocrates response: {socrates_response}"
        check_response = await self.system.termination_checker.run_with_fallback(check_input)

        if "TERMINATE" in check_response:
            self.system.active_mode = "LEGACY"
            return f"{prefix}{socrates_response}\n\n[Class dismissed. Returning to normal mode.]"

        return f"{prefix}{socrates_response}"

    def get_status(self) -> Dict[str, Any]:
        """
        Get system status information.

        Returns:
            Dictionary with status information
        """
        if self.system is None:
            return {"status": "not_initialized"}

        from config.agent_registry import get_registry_stats
        stats = get_registry_stats()

        return {
            "status": "running",
            "interface": self.session_prefix,
            "active_mode": self.system.active_mode,
            "session_id": self.system.session_id,
            "total_agents": stats['total_agents'],
            "worker_agents": stats['worker_agents'],
            "adk_migration": stats['adk_migration_progress']
        }

    def get_agents_info(self) -> str:
        """
        Get formatted information about available agents.

        Returns:
            Formatted string with agent information
        """
        if self.system is None:
            return "System not initialized"

        lines = ["=== Available Agents ===\n"]

        # Orchestrator
        lines.append(f"Smart Orchestrator: {self.system.orchestrator.name}")
        lines.append(f"  Model: {self.system.orchestrator.model}")
        lines.append(f"  Features: Multi-agent coordination, conditional logic\n")

        # Enterprise components
        lines.append("Enterprise Components:")
        lines.append(f"  - Decision Validator ({self.system.decision_validator.model})")
        lines.append(f"  - Ask User Agent ({self.system.ask_user.model})\n")

        # Philosophy
        lines.append("Philosophy Classroom:")
        lines.append(f"  - Socrates ({self.system.socrates.model})")
        lines.append(f"  - TerminationChecker ({self.system.termination_checker.model})\n")

        # Workers
        lines.append(f"Worker Agents ({len(self.system.worker_agents)}):")
        for agent in self.system.worker_agents:
            lines.append(f"  - {agent.name} ({agent.model})")

        return "\n".join(lines)

    @abstractmethod
    async def start(self) -> None:
        """Start the interface. Must be implemented by subclasses."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the interface. Must be implemented by subclasses."""
        pass

    @abstractmethod
    def format_response(self, response: str) -> str:
        """
        Format response for the specific interface.

        Args:
            response: Raw response from agent

        Returns:
            Formatted response for the interface
        """
        pass
