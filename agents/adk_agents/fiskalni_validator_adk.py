"""
Fiskalni Validator ADK Agent

Native ADK implementation of strict quality gate for Croatian e-Invoice (Fiskalizacija 2.0).

Capabilities:
- Chain-of-thought validation protocol
- OIB checksum re-verification
- Mathematical consistency checks
- Business rule validation
- KPD code verification

This is the second agent in the fiscalization pipeline:
Pripremac → Validator → Executor

CRITICAL: This agent operates at temperature 0.0 for maximum determinism.
Its job is to FIND ERRORS, not confirm correctness.

Usage:
    from agents.adk_agents.fiskalni_validator_adk import create_fiskalni_validator_agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    # Create agent
    validator = create_fiskalni_validator_agent()

    # Create runner
    runner = Runner(
        agent=validator,
        app_name="agents",
        session_service=InMemorySessionService()
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


def create_fiskalni_validator_agent(
    model: str = "gemini-2.5-flash",
    credentials=None
) -> LlmAgent:
    """
    Create Fiskalni Validator ADK agent for strict invoice validation.

    This agent specializes in:
    - Chain-of-thought validation with explicit step documentation
    - Zero-tolerance mathematical verification (exact match required)
    - OIB re-validation (defense in depth)
    - Business rule enforcement
    - KPD code verification and confidence checking

    Validation Outcomes:
    - VALID: All checks pass → Forward to Executor
    - NEEDS_REVIEW: Minor issues (KPD confidence) → Human-in-Loop
    - INVALID: Critical errors → Error handler

    Critical Rules:
    - ZERO tolerance for math errors (0.01 EUR = INVALID)
    - Trust NO input - validate EVERYTHING independently
    - Document EVERY validation step explicitly
    - When in doubt, REJECT

    Args:
        model: Gemini model to use (default: "gemini-2.5-flash")
        credentials: Optional OAuth2 credentials.

    Returns:
        LlmAgent instance configured for strict validation

    Example:
        >>> validator = create_fiskalni_validator_agent()
        >>> runner = Runner(agent=validator, app_name="agents", session_service=InMemorySessionService())
        >>> response = await run_agent_simple(validator, "Validiraj: {fiskalni_podaci}")
    """

    # Import ADK tools (individual callables)
    from tools.adk_tools.fiskalizacija_adk_tools import (
        validate_oib,
        verify_tax_calculation,
        check_invoice_number_format,
        # validate_xsd,  # REMOVED: Validator works with data, not XML. Executor handles XML validation.
        search_kpd_code,  # For verifying KPD codes exist
    )

    # Create list of tools (ADK-compatible callables)
    tools = [
        # Re-validation tools (defense in depth)
        validate_oib,
        check_invoice_number_format,
        # Verification tools
        verify_tax_calculation,
        # validate_xsd,  # REMOVED: XML validation is executor's responsibility
        # KPD verification
        search_kpd_code,
    ]

    logger.info(f"Initialized {len(tools)} ADK tools for fiskalni validator agent")

    # Load instruction from file
    instruction_file = os.path.join(
        os.path.dirname(__file__),
        "..",
        "fiskalni_validator",
        "instructions.md"
    )

    try:
        with open(instruction_file, 'r', encoding='utf-8') as f:
            instruction = f.read()
    except Exception as e:
        logger.warning(f"Failed to load instruction file: {e}")
        instruction = """You are Fiskalni Validator, the strict quality gate for Croatian e-Invoice.

YOUR JOB IS TO FIND ERRORS - NOT TO CONFIRM CORRECTNESS.

VALIDATION PROTOCOL (Execute in order):
1. OIB Validation - Both supplier and customer OIBs must pass Module 11
2. Mathematical Consistency - All amounts must match exactly (0.00 EUR tolerance)
3. Business Rules - Dates, invoice number format, required fields
4. KPD Verification - Check KPD codes exist and have good confidence

IMPORTANT: Validate invoice DATA only. Do NOT build or validate XML - that's executor's job.

OUTCOMES:
- VALID: All checks pass → Forward to Executor
- NEEDS_REVIEW: KPD confidence <95% → Human review
- INVALID: Any critical failure → Stop and report

Trust NO input. Validate EVERYTHING. When in doubt, REJECT."""

    # Inject current datetime context for accurate date validation
    instruction = inject_datetime_context(instruction, user_timezone="Europe/Zagreb")

    # Create agent using factory
    # CRITICAL: Temperature 0.0 for deterministic validation
    agent = create_adk_agent(
        name="fiskalni_validator",
        model=model,
        description="Croatian fiscalization validator: strict quality gate for invoice data, zero-tolerance math checks, OIB and KPD verification",
        tools=tools,
        instruction=instruction,
        load_instruction_from_file=False,
        config={
            "temperature": 0.0,  # CRITICAL: Maximum determinism for validation
            "max_tokens": 1536,
        }
    )

    logger.info(f"Fiskalni Validator ADK agent created with {len(tools)} tools")
    logger.info(f"Model: {model}")
    logger.info("CRITICAL: Temperature set to 0.0 for deterministic validation")
    logger.info("Pipeline position: 2/3 (Pripremac -> Validator -> Executor)")
    return agent


# Create singleton instance for easy import
fiskalni_validator_agent = None


def get_fiskalni_validator_agent(
    model: str = "gemini-2.5-flash",
    credentials=None
) -> LlmAgent:
    """
    Get or create singleton Fiskalni Validator agent instance.

    Args:
        model: Gemini model
        credentials: Optional OAuth2 credentials

    Returns:
        LlmAgent instance
    """
    global fiskalni_validator_agent

    if fiskalni_validator_agent is None:
        fiskalni_validator_agent = create_fiskalni_validator_agent(
            model=model,
            credentials=credentials
        )

    return fiskalni_validator_agent


if __name__ == "__main__":
    # Test agent creation
    import asyncio

    async def test():
        agent = create_fiskalni_validator_agent()
        print(f"[OK] Fiskalni Validator ADK agent created: {agent.name}")
        print(f"   Model: {agent.model}")
        print(f"   Description: {agent.description}")
        print(f"   Tools: {len(agent.tools)}")
        print(f"   Instruction preview: {agent.instruction[:200]}...")

        # Display available tools
        print(f"\n[TOOLS] Available Tools:")
        for tool in agent.tools:
            tool_name = getattr(tool, '__name__', str(tool))
            print(f"   - {tool_name}")

        print(f"\n[VALIDATION PROTOCOL] Steps:")
        print("   1. OIB Validation (Module 11 checksum)")
        print("   2. Mathematical Consistency (zero tolerance)")
        print("   3. Business Rules (dates, format, required fields)")
        print("   4. XSD Schema Validation")
        print("   5. KPD Confidence Review")

        print(f"\n[OUTCOMES]:")
        print("   - VALID → Forward to Executor")
        print("   - NEEDS_REVIEW → Human-in-Loop (Telegram)")
        print("   - INVALID → Error Handler")

        print(f"\n[CRITICAL] Temperature: 0.0 (Maximum Determinism)")

    asyncio.run(test())
