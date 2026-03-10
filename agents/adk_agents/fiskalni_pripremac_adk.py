"""
Fiskalni Pripremac ADK Agent

Native ADK implementation of data preparation specialist for Croatian e-Invoice (Fiskalizacija 2.0).

Capabilities:
- OIB validation (Module 11 algorithm)
- VIES VAT number lookup
- KPD code classification via RAG search
- Tax calculation with Decimal precision
- Data normalization (units, currency, dates)

This is the first agent in the fiscalization pipeline:
Pripremac → Validator → Executor

Usage:
    from agents.adk_agents.fiskalni_pripremac_adk import create_fiskalni_pripremac_agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    # Create agent
    pripremac = create_fiskalni_pripremac_agent()

    # Create runner
    runner = Runner(
        agent=pripremac,
        app_name="agents",
        session_service=InMemorySessionService()
    )

    # Execute
    response = await runner.run_async(
        new_message=types.Content(...),
        session_id="session-123",
        user_id="user-123"
    )
"""

from typing import Optional
import logging
import sys
import os

# Add project root to path for standalone testing
if __name__ == "__main__":
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
    from dotenv import load_dotenv
    load_dotenv()

from google.adk.agents import LlmAgent

from agents.adk_agents.adk_agent_factory import create_adk_agent
from agents.adk_agents.datetime_context import inject_datetime_context

logger = logging.getLogger(__name__)


def create_fiskalni_pripremac_agent(
    model: str = "gemini-2.5-flash",
    credentials=None
) -> LlmAgent:
    """
    Create Fiskalni Pripremac ADK agent for invoice data preparation.

    This agent specializes in:
    - Transforming unstructured data into FiskalniPodaci format
    - OIB validation using Module 11 algorithm
    - VAT number lookup via VIES
    - KPD code classification using RAG semantic search
    - Tax calculations with Decimal precision (NEVER LLM arithmetic)
    - Data normalization (units → UN/ECE Rec 20, currency → ISO 4217)

    Critical Rules:
    - NEVER calculate VAT manually - always use calculate_tax tool
    - NEVER guess OIB numbers - always validate or ask user
    - ONLY use search_kpd_code for KPD classification
    - Mark items with <95% KPD confidence for review

    Args:
        model: Gemini model to use (default: "gemini-2.5-flash")
        credentials: Optional OAuth2 credentials. If None, uses token file.

    Returns:
        LlmAgent instance configured for invoice data preparation

    Example:
        >>> pripremac = create_fiskalni_pripremac_agent()
        >>> runner = Runner(agent=pripremac, app_name="agents", session_service=InMemorySessionService())
        >>> from agents.adk_agents.runner_utils import run_agent_simple
        >>> response = await run_agent_simple(pripremac, "Pripremi racun za Info-Tech d.o.o., 5h IT konzultacija, 100 EUR/sat")
    """

    # Import ADK tools (individual callables)
    from tools.adk_tools.fiskalizacija_adk_tools import (
        get_supplier_data,
        generate_invoice_number,
        validate_oib,
        lookup_vies,
        validate_kpd_code,
        search_kpd_code,
        calculate_tax,
        normalize_unit,
        check_invoice_number_format,
    )

    # Create list of tools (ADK-compatible callables)
    tools = [
        # Data loading (ALWAYS FIRST!)
        get_supplier_data,
        # Auto-generation (smart defaults)
        generate_invoice_number,
        # Validation tools
        validate_oib,
        lookup_vies,
        check_invoice_number_format,
        # Classification tools
        validate_kpd_code,  # Validate user-provided KPD code
        search_kpd_code,    # Semantic search KPD catalog (when no code provided)
        # Calculation tools
        calculate_tax,
        # Normalization tools
        normalize_unit,
    ]

    logger.info(f"Initialized {len(tools)} ADK tools for fiskalni pripremac agent")

    # Load instruction from file
    instruction_file = os.path.join(
        os.path.dirname(__file__),
        "..",
        "fiskalni_pripremac",
        "instructions.md"
    )

    try:
        with open(instruction_file, 'r', encoding='utf-8') as f:
            instruction = f.read()
    except Exception as e:
        logger.warning(f"Failed to load instruction file: {e}")
        instruction = """You are Fiskalni Pripremac, a data preparation specialist for Croatian e-Invoice (Fiskalizacija 2.0).

CRITICAL RULES:
1. NEVER calculate VAT manually - ALWAYS use calculate_tax tool
2. NEVER guess OIB numbers - ALWAYS validate with validate_oib or ask user
3. ONLY use search_kpd_code for KPD classification - NEVER guess codes
4. Mark items with KPD confidence <95% for human review

Your job is to transform unstructured invoice data into validated FiskalniPodaci format."""

    # Inject current datetime context for accurate invoice dating
    instruction = inject_datetime_context(instruction, user_timezone="Europe/Zagreb")

    # Create agent using factory
    agent = create_adk_agent(
        name="fiskalni_pripremac",
        model=model,
        description="Croatian fiscalization data prep: validates OIB, classifies KPD codes, calculates VAT with Decimal precision, normalizes invoice data",
        tools=tools,
        instruction=instruction,
        load_instruction_from_file=False,
        config={
            "temperature": 0.3,  # Some flexibility for understanding varied inputs
            "max_tokens": 2048,
        }
    )

    logger.info(f"Fiskalni Pripremac ADK agent created with {len(tools)} tools")
    logger.info(f"Model: {model}")
    logger.info("Pipeline position: 1/3 (Pripremac -> Validator -> Executor)")
    return agent


# Create singleton instance for easy import
fiskalni_pripremac_agent = None


def get_fiskalni_pripremac_agent(
    model: str = "gemini-2.5-flash",
    credentials=None
) -> LlmAgent:
    """
    Get or create singleton Fiskalni Pripremac agent instance.

    Args:
        model: Gemini model
        credentials: Optional OAuth2 credentials

    Returns:
        LlmAgent instance
    """
    global fiskalni_pripremac_agent

    if fiskalni_pripremac_agent is None:
        fiskalni_pripremac_agent = create_fiskalni_pripremac_agent(
            model=model,
            credentials=credentials
        )

    return fiskalni_pripremac_agent


if __name__ == "__main__":
    # Test agent creation
    import asyncio

    async def test():
        agent = create_fiskalni_pripremac_agent()
        print(f"[OK] Fiskalni Pripremac ADK agent created: {agent.name}")
        print(f"   Model: {agent.model}")
        print(f"   Description: {agent.description}")
        print(f"   Tools: {len(agent.tools)}")
        print(f"   Instruction preview: {agent.instruction[:200]}...")

        # Display available tools
        print(f"\n[TOOLS] Available Tools:")
        for tool in agent.tools:
            tool_name = getattr(tool, '__name__', str(tool))
            print(f"   - {tool_name}")

        print(f"\n[CAPABILITIES] Data Preparation Operations:")
        print("   - OIB validation (Module 11)")
        print("   - VIES VAT lookup")
        print("   - KPD code RAG search")
        print("   - Deterministic tax calculation")
        print("   - Unit normalization (UN/ECE Rec 20)")
        print("   - Currency validation (ISO 4217)")

        print(f"\n[PIPELINE] Position:")
        print("   1. Pripremac (YOU) → Validates and normalizes data")
        print("   2. Validator → Strict quality gate")
        print("   3. Executor → Signs and sends to FINA")

    asyncio.run(test())
