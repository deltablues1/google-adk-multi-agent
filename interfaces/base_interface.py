"""
Base Interface for Google Workspace ADK System

Abstract base class that defines the interface contract for different
communication channels (CLI, Telegram, Web API, etc.)
"""

import asyncio
import os
import logging
import re
import time
import uuid
import unicodedata
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Dict, Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from services.voice_fast_path import (
    execute_fast_smart_home_command,
    resolve_voice_smart_home_response,
)
load_dotenv()

logger = logging.getLogger(__name__)

SMART_HOME_KEYWORDS = {
    "svjetlo", "upal", "ugas", "ukljuc", "uključi", "iskljuc", "isključi",
    "utič", "utic", "bojler", "fotelja", "terasa", "boravak", "hodnik",
    "kuhinja", "kupaona", "soba", "film", "nocno", "noćno", "dolazak",
    "odlazak", "pametna kuća", "pametna kuca", "smart home", "scene", "scena",
    # TV / media (preko Home Assistanta). Golo "tv" se NE stavlja ovdje jer
    # substring match hvata "tvoj"/"molitva" — rješava ga _TV_WORD_RE.
    "televizor", "youtube", "jutjub", "netflix", "pojačaj", "pojacaj",
    "stišaj", "stisaj", "glasnoć", "glasnoc", "kanal", "pauziraj",
}

# Word-boundary match for the bare word "tv" ("upali tv", "tv u dnevnoj").
_TV_WORD_RE = re.compile(r"\btv\b")

CHRISTIAN_KEYWORDS = {
    "krsc", "kršć", "biblij", "katekiz", "molitv", "duhovn", "augustin",
    "ignacije", "razluc", "razluč", "ispit savjesti", "examen", "egzamen",
    "papa", "enciklik", "vatikan", "crkv", "kempis", "isus", "kristov",
}

TIME_DATE_KEYWORDS = {
    "koliko je sati", "koji je datum", "koji je dan", "koji dan", "koliko je ura",
    "datum", "vrijeme", "koliko sati"
}

BUSINESS_ORCHESTRATOR_KEYWORDS = {
    "mail", "email", "gmail", "kalendar", "calendar", "drive", "docs",
    "dokument", "dokumenti", "sheet", "sheets", "tablica", "tablice",
    "zadatak", "zadaci", "contacts", "kontakt", "kontakti",
    # Action / ERP tasks that need tools -> must hit the orchestrator upfront.
    # Matched against _normalize_voice_text output, so use ASCII-folded stems.
    "faktura", "fiskaliz", "ponud", "podsjetnik", "podsjeti", "sastanak",
    "posalji", "rezervi", "zakazi", "racun",
}

GENERAL_VOICE_PREFIXES = (
    "sto ",
    "što ",
    "tko ",
    "ko je ",
    "objasni",
    "reci mi",
    "reci nesto",
    "reci nešto",
    "kako ",
    "zasto ",
    "zašto ",
)

VOICE_ROUTING_USER_PREFIXES = (
    "rpi-voice",
    "live-voice",
    "telegram-voice",
)

LOCAL_VOICE_ROUTE = "local_voice_response"
ORCHESTRATOR_VOICE_ROUTE = "orchestrator"
# voice_qa (tool-less) emits this sentinel when the request is actually a task;
# the interface then re-routes the original message to the orchestrator.
ESCALATE_SENTINEL = "[[ESCALATE]]"
VOICE_SMART_HOME_RESPONSE_MODE = os.getenv(
    "VOICE_SMART_HOME_RESPONSE_MODE",
    "none",
).strip().lower()

SMART_HOME_ROOM_ALIASES = {
    "svjetlo_boravak": ("boravak", "dnevni", "dnevni boravak", "dnevnom boravku"),
    "svjetlo_kuhinja": ("kuhinja", "kuhinji"),
    "svjetlo_hodnik": ("hodnik", "hodniku"),
    "svjetlo_kupaona": ("kupaona", "kupaonici", "kupatilo", "kupatilu"),
    "svjetlo_blagavaona": ("blagavaona", "blagovaona", "blagavaonici", "blagovaonici"),
    "svjetlo_ulaz": ("ulaz",),
    "svjetlo_terasa1": ("terasa", "terasi"),
    "svjetlo_vani": ("vani", "dvoriste", "dvoristu"),
    "svjetlo_soba1": ("soba 1", "soba1"),
    "svjetlo_soba2": ("soba 2", "soba2"),
}

SMART_HOME_SPOKEN_NAMES = {
    "svjetlo_boravak": "svjetlo u dnevnom boravku",
    "svjetlo_kuhinja": "svjetlo u kuhinji",
    "svjetlo_hodnik": "svjetlo u hodniku",
    "svjetlo_kupaona": "svjetlo u kupaoni",
    "svjetlo_blagavaona": "svjetlo u blagovaonici",
    "svjetlo_ulaz": "svjetlo na ulazu",
    "svjetlo_terasa1": "svjetlo na terasi",
    "svjetlo_vani": "vanjsko svjetlo",
    "svjetlo_soba1": "svjetlo u sobi 1",
    "svjetlo_soba2": "svjetlo u sobi 2",
}

SMART_HOME_SCENE_ALIASES = {
    "nocno": ("nocno", "noćno"),
    "film": ("film", "kino"),
    "dolazak": ("dolazak", "dosao sam", "došao sam"),
    "odlazak": ("odlazak", "idem van", "izlazim"),
    "kuhanje": ("kuhanje", "kuham", "kuhaj"),
}


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

    def _get_worker_agent(self, agent_name: str):
        """Return a loaded worker agent by name, if present."""
        if not self.system:
            return None
        for agent in self.system.worker_agents:
            if getattr(agent, "name", "") == agent_name:
                return agent
        return None

    @staticmethod
    def _normalize_voice_text(text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text.lower())
        return "".join(ch for ch in normalized if not unicodedata.combining(ch))

    def _should_use_voice_direct_routing(self, user_id: str) -> bool:
        """Enable direct routing only for voice-tagged users when the feature is on."""
        direct_enabled = os.getenv("VOICE_DIRECT_ROUTING", "false").lower() in (
            "1", "true", "yes", "on"
        )
        if not direct_enabled:
            return False
        return user_id.startswith(VOICE_ROUTING_USER_PREFIXES)

    def _match_direct_voice_agent(self, message: str) -> Optional[str]:
        """Pick direct voice target before orchestrator fallback."""
        msg_lower = message.lower()
        if any(kw in msg_lower for kw in self.system.philosophy_keywords):
            return "socrates"
        if any(kw in msg_lower for kw in SMART_HOME_KEYWORDS) or _TV_WORD_RE.search(msg_lower):
            return "smart_home"
        if any(kw in msg_lower for kw in CHRISTIAN_KEYWORDS):
            return "christian_guide"
        if any(kw in msg_lower for kw in TIME_DATE_KEYWORDS):
            return "secretary"
        if msg_lower.startswith(GENERAL_VOICE_PREFIXES):
            return "voice_qa"
        return None

    def _looks_like_business_orchestrator_task(self, message: str) -> bool:
        msg_lower = self._normalize_voice_text(message)
        return any(kw in msg_lower for kw in BUSINESS_ORCHESTRATOR_KEYWORDS)

    async def _speak_working_ack(self) -> None:
        """Speak a short 'working on it' cue before a long orchestrator run.

        The wake-word runner registers `voice_ack_hook` (a blocking
        text->speech function); other interfaces leave it unset, so this is a
        no-op for web/Telegram. Runs in an executor so TTS playback doesn't
        block the event loop.
        """
        hook = getattr(self, "voice_ack_hook", None)
        if not callable(hook):
            return
        text = os.getenv(
            "VOICE_WORKING_ACK_TEXT",
            "Radim na tome. Ovo može potrajati minutu ili dvije.",
        ).strip()
        if not text:
            return
        try:
            await asyncio.get_event_loop().run_in_executor(None, hook, text)
        except Exception:
            logger.debug("Working-ack hook failed", exc_info=True)

    @staticmethod
    def _voice_friendly_error(exc: Exception) -> str:
        """Short spoken-Croatian failure message with a rough cause."""
        low = str(exc).lower()
        if "loop guard" in low:
            import re
            m = re.search(r"tool '([^']+)'", str(exc))
            tool = m.group(1) if m else "jedan od alata"
            return (
                f"Nisam uspio dovršiti zadatak — alat {tool} stalno javlja "
                "grešku pa sam odustao. Pokušaj drugačije formulirati zahtjev."
            )
        if "429" in low or "rate limit" in low or "resource_exhausted" in low or "overloaded" in low:
            return (
                "Nisam uspio — servis za umjetnu inteligenciju je trenutno "
                "preopterećen. Pričekaj minutu pa pokušaj ponovno."
            )
        if "timeout" in low or "timed out" in low or "cancelled" in low:
            return "Nisam uspio — zadatak je predugo trajao pa je prekinut."
        if "401" in low or "403" in low or "authentication" in low or "api key" in low or "permission" in low:
            return (
                "Nisam uspio — imam problem s pristupom servisu, izgleda kao "
                "problem s ovlastima ili ključem."
            )
        if "connection" in low or "network" in low or "dns" in low or "unreachable" in low:
            return "Nisam uspio — ne mogu se spojiti na servis. Provjeri internet vezu."
        if "quota" in low:
            return "Nisam uspio — potrošena je kvota prema servisu za danas ili ovu minutu."
        return (
            "Nisam uspio izvršiti zadatak zbog tehničke greške. "
            "Detalji su zapisani u logu."
        )

    def _is_time_or_date_request(self, message: str) -> bool:
        msg_lower = self._normalize_voice_text(message)
        return any(kw in msg_lower for kw in TIME_DATE_KEYWORDS)

    def _build_time_or_date_response(self, message: str) -> str:
        tz_name = os.getenv("USER_TIMEZONE", "Europe/Zagreb")
        now = datetime.now(ZoneInfo(tz_name))
        msg_lower = message.lower()

        if "datum" in msg_lower or "koji je dan" in msg_lower or "koji dan" in msg_lower:
            return now.strftime("Danas je %A, %d. %m. %Y.")

        return now.strftime("Trenutno je %H:%M.")

    def _classify_voice_route(self, message: str) -> tuple[str, Optional[str]]:
        """
        Lightweight voice pre-router.

        Returns:
            (route_type, route_target)
            route_type:
              - LOCAL_VOICE_ROUTE
              - ORCHESTRATOR_VOICE_ROUTE
              - "agent"
        """
        if self._is_time_or_date_request(message):
            return LOCAL_VOICE_ROUTE, None

        if self._looks_like_business_orchestrator_task(message):
            return ORCHESTRATOR_VOICE_ROUTE, None

        direct_agent = self._match_direct_voice_agent(message)
        if direct_agent in {"socrates", "smart_home", "christian_guide", "secretary"}:
            return "agent", direct_agent

        if direct_agent == "voice_qa":
            return "agent", "voice_qa"

        # Default for anything not clearly a tool/business task: the fast,
        # tool-less voice_qa agent (Claude Sonnet) instead of the heavy 14-tool
        # orchestrator. Real tasks are caught upstream by the business-keyword
        # check; anything that slips through is handled by voice_qa's
        # escalate-to-orchestrator handoff (Phase 2).
        return "agent", "voice_qa"

    def _resolve_voice_smart_home_response(
        self,
        base_response: str,
        response_mode: Optional[str],
    ) -> str:
        return resolve_voice_smart_home_response(base_response, response_mode)

    async def _try_fast_smart_home_response(
        self,
        message: str,
        response_mode: Optional[str] = None,
    ) -> Optional[str]:
        fast_response = await execute_fast_smart_home_command(
            message,
            response_mode=response_mode,
        )
        if fast_response is not None:
            return fast_response

        normalized = self._normalize_voice_text(message)

        if "ugasi sve" in normalized or "sve ugasi" in normalized:
            from tools.adk_tools.mqtt_adk_tools import mqtt_scene_control

            result = await mqtt_scene_control("sve_ugasi")
            if result.get("status") == "ok":
                return self._resolve_voice_smart_home_response(
                    "Ugasio sam sve sto se smije ugasiti.",
                    response_mode,
                )
            return None

        for scene, aliases in SMART_HOME_SCENE_ALIASES.items():
            if any(alias in normalized for alias in aliases):
                from tools.adk_tools.mqtt_adk_tools import mqtt_scene_control

                result = await mqtt_scene_control(scene)
                if result.get("status") == "ok":
                    description = str(result.get("description") or scene).strip()
                    return self._resolve_voice_smart_home_response(
                        f"Uključio sam scenu {description}.",
                        response_mode,
                    )
                return None

        state = None
        if any(token in normalized for token in ("upal", "ukljuc")):
            state = "ON"
        elif any(token in normalized for token in ("ugas", "iskljuc")):
            state = "OFF"

        if state is None:
            return None

        matched_devices = []
        for device_name, aliases in SMART_HOME_ROOM_ALIASES.items():
            if any(alias in normalized for alias in aliases):
                matched_devices.append(device_name)

        if len(matched_devices) != 1:
            return None

        from tools.adk_tools.mqtt_adk_tools import mqtt_switch_control

        device_name = matched_devices[0]
        result = await mqtt_switch_control(device_name, state)
        if result.get("status") != "ok":
            return None

        spoken_name = SMART_HOME_SPOKEN_NAMES.get(device_name, device_name)
        if state == "ON":
            return self._resolve_voice_smart_home_response(
                f"Uključio sam {spoken_name}.",
                response_mode,
            )
        return self._resolve_voice_smart_home_response(
            f"Ugasio sam {spoken_name}.",
            response_mode,
        )

    async def _run_direct_worker_agent(
        self,
        agent_name: str,
        user_id: str,
        session_id: str,
        message: str,
        route_hint: Optional[str] = None,
        response_mode: Optional[str] = None,
    ) -> str:
        """Run a selected worker agent directly, bypassing orchestrator."""
        if agent_name == "smart_home":
            fast_response = await self._try_fast_smart_home_response(
                message,
                response_mode=response_mode,
            )
            if fast_response is not None:
                logger.info("Direct voice route -> smart_home_fast")
                return fast_response

        agent = self._get_worker_agent(agent_name)
        if agent is None:
            logger.warning(
                "Direct voice routing target '%s' not loaded; falling back to orchestrator",
                agent_name,
            )
            return await self.system.orchestrator_helper.run(message)

        from agents.adk_agents.runner_utils import run_agent_simple

        session_service = None
        if self.system.orchestrator_helper:
            session_service = getattr(
                self.system.orchestrator_helper, "session_service", None
            )

        # Keep per-agent ADK sessions isolated. Voice follow-up continuity is
        # handled at the wakeword/router layer; sharing one ADK session across
        # different direct worker agents produced hung runs and unknown-agent
        # events when switching lanes.
        worker_session_id = f"{session_id}-{agent_name}"

        logger.info("Direct voice route -> %s", agent_name)
        worker_message = message
        if agent_name == "smart_home":
            worker_message = (
                "Voice smart-home mode. Interpret the request, execute the home action if the "
                "tools allow it, and answer in one short Croatian sentence suitable for spoken output only when a spoken confirmation is necessary. "
                "If clarification is required, ask only one concise follow-up question.\n\n"
                f"User request: {message}"
            )
        elif agent_name == "secretary":
            worker_message = (
                "Voice utility mode. Answer in Croatian with a short spoken-friendly response. "
                "Prefer one sentence unless the user explicitly asks for more detail.\n\n"
                f"User request: {message}"
            )
        elif agent_name == "voice_qa":
            worker_message = (
                "Voice Q&A mode. Answer the user's question directly in Croatian. "
                "Keep it concise, useful, and suitable for spoken output. "
                "Prefer one short paragraph or at most two short sentences unless the user explicitly asks for depth. "
                "If the user is asking you to PERFORM an action (email, calendar, documents, "
                "smart home, scheduling, invoices), reply with exactly [[ESCALATE]] per your instructions.\n\n"
                f"User question: {message}"
            )
        response = await run_agent_simple(
            agent,
            worker_message,
            session_id=worker_session_id,
            user_id=user_id,
            session_service=session_service,
            app_name="agents",
        )
        if agent_name == "smart_home" and user_id.startswith(VOICE_ROUTING_USER_PREFIXES):
            return self._resolve_voice_smart_home_response(response, response_mode)

        # Phase 2: voice_qa has no tools; when it flags an action request with
        # the [[ESCALATE]] sentinel, re-run the original message through the
        # full orchestrator so the task actually gets executed.
        if agent_name == "voice_qa" and ESCALATE_SENTINEL in response[:200]:
            logger.info("voice_qa escalated to orchestrator: %r", message[:120])
            await self._speak_working_ack()
            return await self.system.run_orchestration(message)

        return response

    async def process_message(
        self,
        user_id: str,
        message: str,
        session_id: Optional[str] = None,
        route_hint: Optional[str] = None,
        response_mode: Optional[str] = None,
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

        _token_marker = None
        try:
            from tools.observability.token_stats import get_token_stats, token_stats_enabled
            if token_stats_enabled():
                _token_marker = get_token_stats().mark()
        except Exception:
            _token_marker = None

        try:
            # Check for mode routing (CLASSROOM vs LEGACY)
            if self.system.active_mode == "CLASSROOM" and not self._should_use_voice_direct_routing(user_id):
                result = await self._process_classroom_mode(message)
            else:
                msg_lower = self._normalize_voice_text(message)
                direct_agent = "socrates" if any(
                    kw in msg_lower for kw in self.system.philosophy_keywords
                ) else None

                if self._should_use_voice_direct_routing(user_id):
                    if route_hint in {"smart_home", "voice_qa", "christian_guide", "socrates", "secretary"}:
                        route_type, route_target = "agent", route_hint
                        logger.info("Pinned voice route -> %s", route_target)
                    else:
                        route_type, route_target = self._classify_voice_route(message)

                    if route_type == LOCAL_VOICE_ROUTE:
                        result = self._build_time_or_date_response(message)
                    elif route_type == "agent" and route_target:
                        result = await self._run_direct_worker_agent(
                            route_target,
                            user_id=user_id,
                            session_id=session_id,
                            message=message,
                            route_hint=route_hint,
                            response_mode=response_mode,
                        )
                    else:
                        # Multi-step orchestrator run — tell the user we're on
                        # it before minutes of silent work.
                        await self._speak_working_ack()
                        result = await self.system.run_orchestration(message)
                elif direct_agent == "socrates":
                    self.system.active_mode = "CLASSROOM"
                    result = await self._process_classroom_mode(message, first_entry=True)
                else:
                    result = await self.system.run_orchestration(message)

            return result

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            # Voice users get a short spoken-Croatian failure with the rough
            # cause; other channels keep the raw error for debugging.
            if self._should_use_voice_direct_routing(user_id):
                return self._voice_friendly_error(e)
            return f"Error processing request: {str(e)}"
        finally:
            if _token_marker is not None:
                try:
                    from tools.observability.token_stats import get_token_stats
                    report = get_token_stats().report(
                        start=_token_marker,
                        title=f"TOKEN USAGE (turn) user={user_id}",
                    )
                    logger.info("[TOKENS]\n%s", report)
                except Exception:
                    pass

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
