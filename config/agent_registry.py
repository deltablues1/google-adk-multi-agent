"""
Modular Agent Registry Pattern

Centralna registracija svih agenata u sustavu.
Omogućava dinamičko učitavanje agenata bez izmjene main.py koda.
"""

from typing import Dict, Any, List, Optional, Type
from dataclasses import dataclass
import importlib
import logging
import os

from config.deployment_config import (
    is_erp_enabled,
    is_rpi_home,
    RPI_HOME_ALLOWED_AGENTS,
)

logger = logging.getLogger(__name__)

FLASH_MODEL = os.getenv("FLASH_MODEL", "gemini-3.5-flash")
PRO_MODEL = os.getenv("PRO_MODEL", "gemini-3.1-pro-preview")
LITE_MODEL = os.getenv("LITE_MODEL", "gemini-3.1-flash-lite")
ORCHESTRATOR_MODEL = os.getenv("ORCHESTRATOR_MODEL", FLASH_MODEL)


@dataclass
class AgentConfig:
    """Konfiguracija pojedinačnog agenta"""

    name: str  # Jedinstveni naziv agenta
    module: str  # Python modul putanja (npr. "agents.mailer.mailer")
    class_name: str  # Naziv klase agenta
    model: str  # Gemini model ("gemini-3.5-flash", "gemini-3.1-pro-preview", "gemini-3.1-pro-preview")
    description: str  # Opis agenta za routing
    tools: List[str]  # Lista alata koje agent koristi
    planner: Optional[str] = None  # Planner tip (npr. "PlanReActPlanner")
    instruction_file: Optional[str] = None  # Putanja do .md instrukcija
    config: Optional[Dict[str, Any]] = None  # Dodatna konfiguracija
    use_adk: bool = False  # Koristi li agent Google ADK (LlmAgent) ili custom BaseAgent
    adk_factory_func: Optional[str] = None  # Factory funkcija za ADK agente (npr. "create_mailer_agent")


# ============================================================================
# AGENT REGISTRY - Centralna registracija svih agenata
# ============================================================================
# MODEL TIERS (Vertex AI, Jun 2026):
#   Tier 1: gemini-3.1-pro-preview  - Complex/critical reasoning (analyst, fiskalni, validation)
#   Tier 2: gemini-3.5-flash (GA)   - Default workhorse incl. orchestrator (beats old 2.5-pro)
#   Tier 4: gemini-3.1-flash-lite (GA) - Cheapest, high-volume simple tasks (smart_home)
#   Note: gemini-3.5-pro not yet available; revisit pro tier when it reaches GA.
# ============================================================================

AGENT_REGISTRY: Dict[str, AgentConfig] = {
    # ========================================================================
    # ORCHESTRATOR AGENT - Router with AutoFlow
    # ========================================================================
    "orchestrator": AgentConfig(
        name="orchestrator",
        module="agents.adk_agents.orchestrator_adk",
        class_name="create_orchestrator_agent",
        model=ORCHESTRATOR_MODEL,  # Tier 3: Flash is sufficient for routing/coordination
        description="Main router agent that delegates tasks to specialized agents. Handles general queries.",
        tools=[],
        instruction_file="agents/orchestrator/instructions.md",
        config={
            "temperature": 0.5,
            "max_tokens": 8192,
        },
        use_adk=True,
        adk_factory_func="create_orchestrator_agent"
    ),

    # ========================================================================
    # WORKSPACE AGENTS - Google Workspace servisi (Tier 3: Flash)
    # ========================================================================

    "mailer": AgentConfig(
        name="mailer",
        module="agents.adk_agents.mailer_adk",
        class_name="create_mailer_agent",
        model=FLASH_MODEL,  # Tier 3: Fast API operations
        description="Handles all Gmail operations: sending, reading, searching emails, managing threads and drafts.",
        tools=["gmail_adk"],
        instruction_file="agents/mailer/instructions.md",
        config={
            "temperature": 0.7,
            "max_tokens": 2048,
        },
        use_adk=True,
        adk_factory_func="create_mailer_agent"
    ),

    "librarian": AgentConfig(
        name="librarian",
        module="agents.adk_agents.librarian_adk",
        class_name="create_librarian_agent",
        model=FLASH_MODEL,  # Tier 3: Fast file search
        description="Manages Google Drive: file operations, sharing, permissions, and natural language search.",
        tools=["drive_adk"],
        instruction_file="agents/librarian/instructions.md",
        config={
            "temperature": 0.3,
            "max_tokens": 1536,
        },
        use_adk=True,
        adk_factory_func="create_librarian_agent"
    ),

    "analyst": AgentConfig(
        name="analyst",
        module="agents.adk_agents.analyst_adk",
        class_name="create_analyst_agent",
        model=PRO_MODEL,  # Tier 2: Precision for data analysis & formulas
        description="Works with Google Sheets: data analysis, formulas, schema-first reading of large tables.",
        tools=["sheets_adk"],
        instruction_file="agents/analyst/instructions.md",
        config={
            "temperature": 0.2,
            "max_tokens": 2048,
        },
        use_adk=True,
        adk_factory_func="create_analyst_agent"
    ),

    "secretary": AgentConfig(
        name="secretary",
        module="agents.adk_agents.secretary_adk",
        class_name="create_secretary_agent",
        model=FLASH_MODEL,  # Tier 3: Fast calendar operations
        description="Manages Google Calendar: events, scheduling, timezone handling, conflict resolution.",
        tools=["calendar_adk"],
        instruction_file="agents/secretary/instructions.md",
        config={
            "temperature": 0.3,
            "max_tokens": 1536,
        },
        use_adk=True,
        adk_factory_func="create_secretary_agent"
    ),

    "rolodex": AgentConfig(
        name="rolodex",
        module="agents.adk_agents.rolodex_adk",
        class_name="create_rolodex_agent",
        model=FLASH_MODEL,  # Tier 3: Fast contact lookup
        description="Manages Google Contacts: search, find emails, manage address book.",
        tools=["contacts_adk"],
        instruction_file="agents/rolodex/instructions.md",
        config={
            "temperature": 0.2,
            "max_tokens": 1024,
        },
        use_adk=True,
        adk_factory_func="create_rolodex_agent"
    ),

    "tracker": AgentConfig(
        name="tracker",
        module="agents.adk_agents.tracker_adk",
        class_name="create_tracker_agent",
        model=FLASH_MODEL,  # Tier 3: Fast task management
        description="Manages Google Tasks: creating, completing, organizing tasks and task lists.",
        tools=["tasks_adk"],
        instruction_file="agents/tracker/instructions.md",
        config={
            "temperature": 0.3,
            "max_tokens": 1024,
        },
        use_adk=True,
        adk_factory_func="create_tracker_agent"
    ),

    # ========================================================================
    # FINANCE & OPERATIONS AGENTS
    # ========================================================================

    "expense": AgentConfig(
        name="expense",
        module="agents.adk_agents.expense_adk",
        class_name="create_expense_agent",
        model=FLASH_MODEL,  # Tier 3: Fast multimodal OCR
        description="Receipt processing specialist using Gemini Flash OCR. Extracts structured data from receipt images (merchant, date, amount, items, category), validates with confidence scoring, and saves to Google Sheets. Handles Croatian language receipts with automatic categorization.",
        tools=["vision_mcp", "drive_adk", "sheets_adk"],
        instruction_file="agents/expense/instructions.md",
        config={
            "temperature": 0.3,
            "max_tokens": 2048,
        },
        use_adk=True,
        adk_factory_func="create_expense_agent"
    ),

    # ========================================================================
    # FISKALIZACIJA 2.0 AGENTS - Croatian e-Invoice Pipeline
    # ========================================================================

    "fiskalni_pripremac": AgentConfig(
        name="fiskalni_pripremac",
        module="agents.adk_agents.fiskalni_pripremac_adk",
        class_name="create_fiskalni_pripremac_agent",
        model=FLASH_MODEL,  # Tier 3: Fast data preparation
        description="Invoice data preparation specialist for Croatian fiscalization (Fiskalizacija 2.0). Validates OIB numbers using Module 11 algorithm, looks up VAT status in VIES, classifies products/services using KPD RAG search, calculates taxes with Decimal precision, and normalizes data to UBL 2.1 / HR-FISK 2.0 standards. Keywords: fiskalizacija, racun, faktura, invoice, OIB, PDV, VAT.",
        tools=["fiskalizacija_adk"],
        instruction_file="agents/fiskalni_pripremac/instructions.md",
        config={
            "temperature": 0.3,
            "max_tokens": 2048,
        },
        use_adk=True,
        adk_factory_func="create_fiskalni_pripremac_agent"
    ),

    "fiskalni_validator": AgentConfig(
        name="fiskalni_validator",
        module="agents.adk_agents.fiskalni_validator_adk",
        class_name="create_fiskalni_validator_agent",
        model=PRO_MODEL,  # Tier 2: Thinking mode for ZERO-tolerance validation
        description="Strict quality gate for Croatian fiscalization. Performs chain-of-thought validation with ZERO tolerance for errors. Re-validates OIB checksums, verifies tax calculations exactly (0.00 EUR tolerance), enforces business rules, and validates XML against XSD schemas. Returns VALID, NEEDS_REVIEW, or INVALID.",
        tools=["fiskalizacija_adk"],
        instruction_file="agents/fiskalni_validator/instructions.md",
        config={
            "temperature": 0.0,
            "max_tokens": 1536,
        },
        use_adk=True,
        adk_factory_func="create_fiskalni_validator_agent"
    ),

    "fiskalni_executor": AgentConfig(
        name="fiskalni_executor",
        module="agents.adk_agents.fiskalni_executor_adk",
        class_name="create_fiskalni_executor_agent",
        model=PRO_MODEL,  # Tier 2: Critical signing operations, must not fail
        description="Final execution agent for Croatian fiscalization. Checks idempotency via ledger, builds UBL XML, signs with XAdES-BES digital signature, submits to FINA via SOAP with circuit breaker, parses JIR response, generates QR code, and maintains audit ledger. Includes retry queue with exponential backoff and 48h deadline.",
        tools=["fiskalizacija_adk"],
        instruction_file="agents/fiskalni_executor/instructions.md",
        config={
            "temperature": 0.1,
            "max_tokens": 2048,
        },
        use_adk=True,
        adk_factory_func="create_fiskalni_executor_agent"
    ),

    # ========================================================================
    # RESEARCH & CONTENT AGENTS
    # ========================================================================

    "researcher": AgentConfig(
        name="researcher",
        module="agents.adk_agents.researcher_adk",
        class_name="create_researcher_agent",
        model=FLASH_MODEL,  # Tier 3: Fast web research
        description="Deep web research using Google Search Grounding, YouTube transcripts, and web scraping. Supports multiple research modes.",
        tools=["research_adk"],
        instruction_file="agents/researcher/instructions.md",
        config={
            "temperature": 0.6,
            "max_tokens": 8192,
        },
        use_adk=True,
        adk_factory_func="create_researcher_agent"
    ),

    "scribe": AgentConfig(
        name="scribe",
        module="agents.adk_agents.scribe_adk",
        class_name="create_scribe_agent",
        model=FLASH_MODEL,  # Tier 3: Fast document creation
        description="Google Docs specialist: creates, formats, and manages documents with professional quality.",
        tools=["docs_adk"],
        instruction_file="agents/scribe/instructions.md",
        config={
            "temperature": 0.7,
            "max_tokens": 4096,
        },
        use_adk=True,
        adk_factory_func="create_scribe_agent"
    ),

    "scraper": AgentConfig(
        name="scraper",
        module="agents.adk_agents.scraper_adk",
        class_name="create_scraper_agent",
        model=FLASH_MODEL,  # Tier 3: Fast data extraction
        description="Web scraping specialist for extracting structured data from websites.",
        tools=["research_adk"],
        instruction_file="agents/scraper/instructions.md",
        config={
            "temperature": 0.3,
            "max_tokens": 2048,
        },
        use_adk=True,
        adk_factory_func="create_scraper_agent"
    ),

    "synthesizer": AgentConfig(
        name="synthesizer",
        module="agents.adk_agents.synthesizer_adk",
        class_name="create_synthesizer_agent",
        model=FLASH_MODEL,  # Tier 3: Flash 3 is capable enough for quality writing
        description="Professional editor and technical writer. Transforms raw research notes into cohesive, high-quality documents. Adapts tone to format (Executive Summary, Technical Report, Blog Post). Preserves citations and avoids hallucinations.",
        tools=[],
        instruction_file="agents/synthesizer/instructions.md",
        config={
            "temperature": 0.7,
            "max_tokens": 8192,
        },
        use_adk=True,
        adk_factory_func="create_synthesizer_agent"
    ),

    "skladistar": AgentConfig(
        name="skladistar",
        module="agents.adk_agents.skladistar_adk",
        class_name="create_skladistar_agent",
        model=FLASH_MODEL,  # Tier 2: fast voice lane, small 4-tool ERP belt
        description="Warehouse (skladište) voice specialist: stock queries, stock adjustments and new product creation with spoken confirmation. Keywords: skladište, zaliha, zalihe, artikl, inventura, lager, dodaj na stanje, skini sa stanja, koliko imam.",
        tools=["erp_adk"],
        instruction_file="agents/skladistar/instructions.md",
        config={
            "temperature": 0.2,
            "max_tokens": 1024,
        },
        use_adk=True,
        adk_factory_func="create_skladistar_agent"
    ),

    "voice_qa": AgentConfig(
        name="voice_qa",
        module="agents.adk_agents.voice_qa_adk",
        class_name="create_voice_qa_agent",
        model=FLASH_MODEL,
        description="Fast spoken Q&A specialist for general knowledge and everyday questions without tool use.",
        tools=[],
        instruction_file="agents/voice_qa/instructions.md",
        config={
            "temperature": 0.4,
            "max_tokens": 2048,
        },
        use_adk=True,
        adk_factory_func="create_voice_qa_agent"
    ),

    # ========================================================================
    # PHILOSOPHY & EDUCATION AGENTS
    # ========================================================================

    "socrates": AgentConfig(
        name="socrates",
        module="agents.adk_agents.socrates_adk",
        class_name="create_socrates_agent",
        model=PRO_MODEL,  # Tier 2: deeper philosophical reasoning for voice (RAG stays on Gemini)
        description="Socratic dialogue specialist. Uses Socratic method to teach through questions, not answers. Deep philosophical reasoning. Philosophy knowledge base (RAG). Keywords: Sokrat, Socrates, filozofija, philosophy.",
        tools=["philosophy_rag"],
        instruction_file=None,
        config={
            "temperature": 0.7,
            "max_tokens": 2048,
        },
        use_adk=True,
        adk_factory_func="create_socrates_agent"
    ),

    "christian_guide": AgentConfig(
        name="christian_guide",
        module="agents.adk_agents.christian_guide_adk",
        class_name="create_christian_guide_agent",
        model=PRO_MODEL,  # Tier 2: deeper theological reasoning for voice (RAG stays on Gemini)
        description="Christian spiritual guide with optional RAG knowledge base. Helps with Christian theology, Scripture-based reflection, discernment, prayer, examen, and guided spiritual exercises. Keywords: krscanstvo, krscanski, kršćanstvo, kršćanski, duhovno, duhovnost, molitva, examen, razlucivanje, razlučivanje, Biblija, Katekizam, Augustin, Ignacije.",
        tools=["christian_rag"],
        instruction_file="agents/christian_guide/instructions.md",
        config={
            "temperature": 0.5,
            "max_tokens": 2048,
        },
        use_adk=True,
        adk_factory_func="create_christian_guide_agent"
    ),

    # ========================================================================
    # MARKETING & ADVERTISING AGENTS
    # ========================================================================

    "marketing": AgentConfig(
        name="marketing",
        module="agents.adk_agents.marketing_adk",
        class_name="create_marketing_agent",
        model=FLASH_MODEL,  # Tier 3: Fast creative ideation
        description="Google Ads specialist with Vertex AI visual generation. Creates images/videos, hosts on YouTube, and creates ad campaigns. CRITICAL: Human-in-the-loop workflow - always gets user approval before proceeding. Campaigns start in PAUSED state for safety.",
        tools=["marketing_adk"],
        instruction_file="agents/marketing/instructions.md",
        config={
            "temperature": 0.8,
            "max_tokens": 2048,
        },
        use_adk=True,
        adk_factory_func="create_marketing_agent"
    ),

    # ========================================================================
    # SCHEDULER AGENT - Recurring/Scheduled Tasks
    # ========================================================================

    "scheduler": AgentConfig(
        name="scheduler",
        module="agents.adk_agents.scheduler_adk",
        class_name="create_scheduler_agent",
        model=FLASH_MODEL,  # Tier 3: Fast schedule management
        description="Manages scheduled/recurring tasks. Can schedule any agent request to run on a cron schedule (e.g., weekdays at 9am), at intervals (e.g., every hour), or at a specific date/time. Keywords: zakaži, schedule, ponavljaj, recurring, timer, cron, svaki dan, svaki tjedan.",
        tools=["scheduler_adk"],
        instruction_file="agents/scheduler/instructions.md",
        config={
            "temperature": 0.3,
            "max_tokens": 1536,
        },
        use_adk=True,
        adk_factory_func="create_scheduler_agent"
    ),

    # ========================================================================
    # ENTERPRISE ORCHESTRATION AGENTS
    # ========================================================================

    "decision_validator": AgentConfig(
        name="decision_validator",
        module="agents.adk_agents.decision_validator",
        class_name="create_decision_validator",
        model=FLASH_MODEL,  # Tier 3: Fast boolean decisions
        description="Enterprise precondition validator that checks conditions before actions are executed. Returns CONDITION_MET or CONDITION_FAILED.",
        tools=[],
        instruction_file=None,
        config={
            "temperature": 0.1,
            "max_tokens": 1024,
        },
        use_adk=True,
        adk_factory_func="create_decision_validator"
    ),

    "ask_user": AgentConfig(
        name="ask_user",
        module="agents.adk_agents.ask_user_agent",
        class_name="create_ask_user_agent",
        model=FLASH_MODEL,  # Tier 3: Fast response generation
        description="Handles failed preconditions by presenting users with clear alternatives when workflows cannot proceed automatically.",
        tools=[],
        instruction_file=None,
        config={
            "temperature": 0.4,
            "max_tokens": 1024,
        },
        use_adk=True,
        adk_factory_func="create_ask_user_agent"
    ),

    # ========================================================================
    # FISKALIZACIJA - Croatian Invoice Fiscalization
    # ========================================================================

    "smart_home": AgentConfig(
        name="smart_home",
        module="agents.adk_agents.smart_home_adk",
        class_name="create_smart_home_agent",
        model=LITE_MODEL,  # Tier 4: Cheapest GA model — simple MQTT commands, high-volume
        description="Smart home MQTT specialist: controls lights (15), outlets (14), dimmer (1) via ESP32-IO. Keywords: svjetlo, upali, ugasi, uključi, isključi, utičnica, bojler, pametna kuća, smart home, scena, film, noćno.",
        tools=["mqtt_adk"],
        instruction_file="agents/smart_home/instructions.md",
        config={
            "temperature": 0.3,
            "max_tokens": 1536,
        },
        use_adk=True,
        adk_factory_func="create_smart_home_agent"
    ),

    "fiskalizacija": AgentConfig(
        name="fiskalizacija",
        module="agents.adk_agents.fiskalizacija_adk",
        class_name="create_fiskalizacija_agent",
        model=FLASH_MODEL,  # Tier 3: Fast wrapper (critical path is deterministic)
        description="Croatian invoice fiscalization (Fiskalizacija 2.0) with hybrid architecture: LLM preparation/validation + deterministic execution (NO LLM for signing/SOAP). Keywords: fiskalizacija, racun, faktura, invoice, JIR, ZKI, FINA, PDV, VAT.",
        tools=["fiskalizacija_adk"],
        instruction_file=None,
        config={
            "temperature": 0.1,
            "max_tokens": 2048,
        },
        use_adk=True,
        adk_factory_func="create_fiskalizacija_agent"
    ),
}


# ============================================================================
# REGISTRY FUNCTIONS
# ============================================================================

def get_agent_config(agent_name: str) -> Optional[AgentConfig]:
    """
    Dohvaća konfiguraciju agenta iz registra

    Args:
        agent_name: Naziv agenta

    Returns:
        AgentConfig objekt ili None ako agent ne postoji
    """
    # ERP gating happens at the tool-belt level (conditional ERP tools per
    # agent), not by hiding agents from the registry.
    # On the RPi home profile, only whitelisted agents are exposed.
    if is_rpi_home() and agent_name not in RPI_HOME_ALLOWED_AGENTS:
        return None
    return AGENT_REGISTRY.get(agent_name)


def get_all_agent_names() -> List[str]:
    """
    Dohvaća listu svih naziva agenata u registru

    Returns:
        Lista naziva agenata
    """
    return [
        name for name in AGENT_REGISTRY.keys()
        if get_agent_config(name) is not None
    ]


def get_worker_agent_names() -> List[str]:
    """
    Dohvaća listu worker agenata (svi osim orchestration infrastructure agenata)

    Worker agenti su specijalizirani agenti koji obavljaju specifične zadatke
    (Gmail, Calendar, Drive, Fiskalizacija, itd.).

    Excludes:
    - orchestrator (router)
    - decision_validator (orchestration helper)
    - ask_user (orchestration helper)
    - fiskalni_pripremac (internal - use fiskalizacija instead)
    - fiskalni_validator (internal - use fiskalizacija instead)
    - fiskalni_executor (internal - use fiskalizacija instead)

    NOTE: Use 'fiskalizacija' agent for ALL fiscalization requests!
    It coordinates the complete pipeline via execute_fiscalization tool.
    The individual fiskalni_* agents are internal components and should NOT
    be called directly by the orchestrator - they don't share data properly.

    Returns:
        Lista naziva worker agenata
    """
    excluded_agents = {
        # Orchestration infrastructure
        "orchestrator",
        "decision_validator",
        "ask_user",
        # Internal fiscalization components (use 'fiskalizacija' wrapper instead)
        "fiskalni_pripremac",
        "fiskalni_validator",
        "fiskalni_executor",
    }
    worker_names = [name for name in AGENT_REGISTRY.keys() if name not in excluded_agents]

    # RPi home profile: restrict to the conversational/home whitelist
    if is_rpi_home():
        worker_names = [n for n in worker_names if n in RPI_HOME_ALLOWED_AGENTS]

    return worker_names


def get_agents_by_model(model: str) -> List[str]:
    """
    Dohvaća agente koji koriste određeni model

    Args:
        model: Naziv modela (npr. "gemini-3.5-flash")

    Returns:
        Lista naziva agenata
    """
    return [
        name for name, config in AGENT_REGISTRY.items()
        if get_agent_config(name) is not None
        if config.model == model
    ]


def create_agent_instance(agent_name: str, **kwargs) -> Any:
    """
    Dinamički kreira instancu agenta iz registra

    Podržava dva pristupa:
    1. Legacy Custom BaseAgent (use_adk=False)
    2. Native Google ADK LlmAgent (use_adk=True)

    Args:
        agent_name: Naziv agenta
        **kwargs: Dodatni argumenti za konstruktor agenta

    Returns:
        Instanca agenta (BaseAgent ili LlmAgent)

    Raises:
        ValueError: Ako agent nije pronađen u registru
        ImportError: Ako modul ne može biti učitan
        AttributeError: Ako klasa/funkcija ne postoji u modulu
    """
    config = get_agent_config(agent_name)
    if not config:
        raise ValueError(f"Agent '{agent_name}' not found in registry")

    try:
        # Dinamički učitaj modul
        module = importlib.import_module(config.module)

        # Check if agent uses ADK
        if config.use_adk:
            # ========================================
            # ADK AGENT PATH (NEW)
            # ========================================
            logger.info(f"Creating ADK agent: {agent_name}")

            # Dohvati factory funkciju
            factory_func_name = config.adk_factory_func or config.class_name
            factory_func = getattr(module, factory_func_name)

            # Kreiraj ADK agenta kroz factory
            # ADK factory functions obično uzimaju samo model parameter
            agent_instance = factory_func(model=config.model, **kwargs)

            logger.info(f"[OK] ADK agent created: {agent_name} ({config.model})")
            return agent_instance

        else:
            # ========================================
            # LEGACY CUSTOM BASEAGENT PATH (OLD)
            # ========================================
            logger.info(f"Creating legacy agent: {agent_name}")

            # Dohvati klasu iz modula
            agent_class = getattr(module, config.class_name)

            # Kreiraj instancu
            agent_instance = agent_class(
                name=config.name,
                model=config.model,
                instruction_file=config.instruction_file,
                config=config.config,
                **kwargs
            )

            logger.info(f"Legacy agent created: {agent_name}")
            return agent_instance

    except ImportError as e:
        logger.error(f"Failed to import module '{config.module}': {e}")
        raise

    except AttributeError as e:
        logger.error(f"Class/Function '{config.class_name}' not found in module '{config.module}': {e}")
        raise

    except Exception as e:
        logger.error(f"Failed to create agent '{agent_name}': {e}")
        import traceback
        traceback.print_exc()
        raise


def generate_orchestrator_routing_guide() -> str:
    """
    Generira routing guide za Orchestrator agenta iz registra

    Returns:
        Markdown tekst s listom agenata i njihovim opisima
    """
    lines = ["# Available Agents for Delegation\n"]

    for name in get_worker_agent_names():
        config = get_agent_config(name)
        lines.append(f"## {name.upper()}")
        lines.append(f"**Model:** {config.model}")
        lines.append(f"**Description:** {config.description}")
        lines.append(f"**Tools:** {', '.join(config.tools)}")
        if config.planner:
            lines.append(f"**Planner:** {config.planner}")
        lines.append("")

    return "\n".join(lines)


def validate_registry() -> bool:
    """
    Validira registry - provjerava postoje li svi moduli i klase

    Returns:
        True ako je registry validan
    """
    all_valid = True

    for name, config in AGENT_REGISTRY.items():
        try:
            # Provjeri postoji li modul
            module = importlib.import_module(config.module)

            # Provjeri postoji li klasa
            if not hasattr(module, config.class_name):
                logger.error(
                    f"Agent '{name}': Class '{config.class_name}' not found in module '{config.module}'"
                )
                all_valid = False

        except ImportError as e:
            logger.error(f"Agent '{name}': Failed to import module '{config.module}': {e}")
            all_valid = False

    return all_valid


# ============================================================================
# REGISTRY STATISTICS
# ============================================================================

def get_registry_stats() -> Dict[str, Any]:
    """
    Dohvaća statistiku o registru

    Returns:
        Dictionary sa statistikama
    """
    # Count ADK vs Legacy agents
    adk_agents = [name for name, config in AGENT_REGISTRY.items() if config.use_adk]
    legacy_agents = [name for name, config in AGENT_REGISTRY.items() if not config.use_adk]

    stats = {
        "total_agents": len(AGENT_REGISTRY),
        "worker_agents": len(get_worker_agent_names()),
        "flash_agents": len(get_agents_by_model(FLASH_MODEL)),
        "pro_agents": len(get_agents_by_model(PRO_MODEL)),
        "flash_lite_agents": len(get_agents_by_model(LITE_MODEL)),
        "agents_with_planner": sum(1 for c in AGENT_REGISTRY.values() if c.planner),
        "adk_agents": len(adk_agents),
        "legacy_agents": len(legacy_agents),
        "adk_agent_names": adk_agents,
        "legacy_agent_names": legacy_agents,
        "adk_migration_progress": f"{len(adk_agents)}/{len(AGENT_REGISTRY)} ({len(adk_agents)*100//len(AGENT_REGISTRY)}%)"
    }

    return stats
