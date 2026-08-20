"""
Fiskalni Executor ADK Agent

Native ADK implementation of signing and submission specialist for Croatian e-Invoice (Fiskalizacija 2.0).

Capabilities:
- Idempotency check via invoice ledger
- FINA RacunZahtjev XML generation (HR format)
- ZKI calculation (protective code)
- XAdES-BES digital signing
- FINA SOAP submission with circuit breaker
- QR code generation for verification
- PDF invoice generation (NEW!)

This is the third (final) agent in the fiscalization pipeline:
Pripremac → Validator → Executor

CRITICAL: This agent ONLY executes. It does NOT make content decisions.
If something looks wrong, it STOPS and returns to Validator.

Usage:
    from agents.adk_agents.fiskalni_executor_adk import create_fiskalni_executor_agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    # Create agent
    executor = create_fiskalni_executor_agent()

    # Create runner
    runner = Runner(
        agent=executor,
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

logger = logging.getLogger(__name__)


def create_fiskalni_executor_agent(
    model: str = "gemini-3.1-pro-preview",  # Tier 1: Critical signing operations
    credentials=None
) -> LlmAgent:
    """
    Create Fiskalni Executor ADK agent for invoice signing and submission.

    This agent specializes in:
    - Idempotency checking (prevent duplicate fiscalization)
    - UBL 2.1 + HR-FISK 2.0 XML generation
    - C14N canonicalization
    - XAdES-BES digital signing
    - FINA SOAP submission with circuit breaker
    - JIR parsing and QR code generation
    - Retry queue management

    Execution Protocol (Strict Order):
    1. Check ledger for existing JIR (idempotency)
    2. Load certificate
    3. Calculate ZKI (protective code)
    4. Build FINA RacunZahtjev XML (with ZKI)
    5. Sign with XAdES-BES
    6. Submit to FINA
    7. Parse response (JIR or error)
    8. Generate QR code
    9. Save to ledger
    10. Generate PDF invoice (NEW!)

    Critical Rules:
    - ALWAYS check idempotency FIRST
    - NEVER sign without valid certificate
    - NEVER modify invoice content (return to Validator)
    - Handle FINA errors appropriately (retry vs reject)

    Args:
        model: Gemini model to use (default: "gemini-2.5-pro" for critical ops)
        credentials: Optional OAuth2 credentials.

    Returns:
        LlmAgent instance configured for invoice execution

    Example:
        >>> executor = create_fiskalni_executor_agent()
        >>> runner = Runner(agent=executor, app_name="agents", session_service=InMemorySessionService())
        >>> response = await run_agent_simple(executor, "Fiskaliziraj: {validated_fiskalni_podaci}")
    """

    # Import ADK tools (individual callables)
    from tools.adk_tools.fiskalizacija_adk_tools import (
        # Ledger tools
        check_invoice_ledger,
        save_invoice_ledger,
        add_to_retry_queue,
        # XML tools
        build_ubl_invoice,
        validate_xsd,
        canonicalize_xml,
        # Signing tools
        load_certificate,
        sign_xades,
        calculate_zki,
        verify_xml_signature,
        # Communication tools
        send_fina_soap,
        parse_fina_response,
        generate_qr_code,
        # PDF generation (NEW!)
        generate_invoice_pdf,
    )

    # Create list of tools (ADK-compatible callables)
    tools = [
        # Idempotency
        check_invoice_ledger,
        save_invoice_ledger,
        # XML construction
        build_ubl_invoice,
        validate_xsd,
        canonicalize_xml,
        # Signing (Phase 3 - IMPLEMENTED)
        load_certificate,
        sign_xades,
        calculate_zki,
        verify_xml_signature,
        # Communication
        send_fina_soap,
        parse_fina_response,
        generate_qr_code,
        # PDF generation (Phase 6 - NEW!)
        generate_invoice_pdf,
        # Retry queue
        add_to_retry_queue,
    ]

    logger.info(f"Initialized {len(tools)} ADK tools for fiskalni executor agent")

    # Load instruction from file
    instruction_file = os.path.join(
        os.path.dirname(__file__),
        "..",
        "fiskalni_executor",
        "instructions.md"
    )

    try:
        with open(instruction_file, 'r', encoding='utf-8') as f:
            instruction = f.read()
    except Exception as e:
        logger.warning(f"Failed to load instruction file: {e}")
        instruction = """You are Fiskalni Executor, the final execution agent for Croatian e-Invoice.

You ONLY execute. You do NOT make content decisions.

EXECUTION PROTOCOL (Strict Order):
1. check_invoice_ledger - If exists, return existing JIR
2. load_certificate - Load from Secret Manager
3. calculate_zki - Calculate protective code (ZKI)
4. build_ubl_invoice - Generate FINA XML (with ZKI)
5. sign_xades - Apply XAdES-BES signature
6. send_fina_soap - Submit to FINA
7. parse_fina_response - Extract JIR or errors
8. generate_qr_code - Create verification QR
9. save_invoice_ledger - Record for idempotency
10. generate_invoice_pdf - Generate customer PDF (NEW!)

CRITICAL RULES:
- ALWAYS check idempotency FIRST
- NEVER sign without valid certificate
- NEVER modify invoice content
- On error: return to Validator or add to retry queue"""

    # Inject current datetime context for accurate execution timestamps
    # Datum/vrijeme se NE ubacuje ovdje: to bi zamrznulo sat na trenutak
    # kad je agent stvoren. Predaje se predložak, a tvornica ga omota u
    # ADK instruction provider koji ga renderira pri svakom pozivu.

    # Create agent using factory
    agent = create_adk_agent(
        name="fiskalni_executor",
        model=model,
        description="Croatian fiscalization executor: signs invoices with XAdES-BES, submits to FINA, generates PDF with JIR/QR",
        tools=tools,
        instruction=instruction,
        load_instruction_from_file=False,
        config={
            "temperature": 0.1,  # Minimal creativity - just execute
            "max_tokens": 2048,
        }
    )

    logger.info(f"Fiskalni Executor ADK agent created with {len(tools)} tools")
    logger.info(f"Model: {model}")
    logger.info("Pipeline position: 3/3 (Pripremac -> Validator -> Executor)")
    logger.info("This agent EXECUTES only - no content decisions")
    return agent


# Create singleton instance for easy import
fiskalni_executor_agent = None


def get_fiskalni_executor_agent(
    model: str = "gemini-3.5-flash",
    credentials=None
) -> LlmAgent:
    """
    Get or create singleton Fiskalni Executor agent instance.

    Args:
        model: Gemini model
        credentials: Optional OAuth2 credentials

    Returns:
        LlmAgent instance
    """
    global fiskalni_executor_agent

    if fiskalni_executor_agent is None:
        fiskalni_executor_agent = create_fiskalni_executor_agent(
            model=model,
            credentials=credentials
        )

    return fiskalni_executor_agent


if __name__ == "__main__":
    # Test agent creation
    import asyncio

    async def test():
        agent = create_fiskalni_executor_agent()
        print(f"[OK] Fiskalni Executor ADK agent created: {agent.name}")
        print(f"   Model: {agent.model}")
        print(f"   Description: {agent.description}")
        print(f"   Tools: {len(agent.tools)}")
        print(f"   Instruction preview: {agent.instruction[:200]}...")

        # Display available tools
        print(f"\n[TOOLS] Available Tools:")
        for tool in agent.tools:
            tool_name = getattr(tool, '__name__', str(tool))
            print(f"   - {tool_name}")

        print(f"\n[EXECUTION PROTOCOL] Steps:")
        print("   1.  check_invoice_ledger (idempotency)")
        print("   2.  build_ubl_invoice")
        print("   3.  validate_xsd")
        print("   4.  canonicalize_xml")
        print("   5.  load_certificate")
        print("   6.  sign_xades")
        print("   7.  send_fina_soap")
        print("   8.  parse_fina_response")
        print("   9.  generate_qr_code")
        print("   10. save_invoice_ledger")

        print(f"\n[FINA ENDPOINTS]:")
        print("   Sandbox: https://cistest.apis-it.hr:8449/FiskalizacijaServiceTest")
        print("   Production: https://cis.porezna-uprava.hr:8449/FiskalizacijaService")

        print(f"\n[RESILIENCE]:")
        print("   - Circuit breaker (5 failures → open)")
        print("   - Exponential retry (1m, 2m, 4m, ...)")
        print("   - 48h deadline (Croatian law)")

    asyncio.run(test())
