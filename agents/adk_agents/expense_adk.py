"""
Expense ADK Agent

Native ADK implementation of receipt processing specialist using LlmAgent primitive.
Uses Gemini Flash multimodal OCR for cost-effective expense tracking.

Capabilities:
- Multimodal OCR with Gemini 2.0 Flash (Flash-First strategy)
- Automatic categorization and validation
- Google Sheets integration for expense tracking
- 1400x cost reduction vs Document AI (~$0.00007 per receipt)

Usage:
    from agents.adk_agents.expense_adk import create_expense_agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    # Create agent
    expense = create_expense_agent()

    # Create runner
    runner = Runner(
        agent=expense,
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


def create_expense_agent(
    model: str = "gemini-2.5-flash",
    credentials=None
) -> LlmAgent:
    """
    Create Expense ADK agent for receipt processing operations.

    This agent specializes in:
    - Multimodal OCR with Gemini Flash (cost-effective: $0.00007/receipt)
    - Structured data extraction (merchant, date, amount, items, category)
    - Automatic expense categorization (Hrana, Prijevoz, Ured, Režije, Ostalo)
    - Confidence-based validation workflow (auto-save ≥80%, manual review <80%)
    - Google Sheets integration for expense tracking
    - Drive folder monitoring for automatic processing

    Flash-First Strategy:
    - Primary: Gemini 2.0 Flash for OCR (99.93% cost savings vs Document AI)
    - No fallback to Document AI (user confirmed)
    - Pydantic schema for guaranteed structured output

    Args:
        model: Gemini model to use (default: "gemini-2.0-flash-exp")
        credentials: Optional OAuth2 credentials. If None, uses token file.

    Returns:
        LlmAgent instance configured for expense operations

    Example:
        >>> expense = create_expense_agent()
        >>> runner = Runner(agent=expense, app_name="agents", session_service=InMemorySessionService())
        >>> # Use runner_utils for simplified execution
        >>> from agents.adk_agents.runner_utils import run_agent_simple
        >>> response = await run_agent_simple(expense, "Process this receipt: [image_data]")
    """

    # Import ADK tools (individual callables)
    from tools.adk_tools.vision_adk_tools import (
        extract_receipt_data,
        categorize_expense
    )
    from tools.adk_tools.drive_adk_tools import (
        drive_search_files,
        drive_get_file,
        drive_upload_file
    )
    from tools.adk_tools.sheets_adk_tools import (
        sheets_get_values,
        sheets_append_values,
        sheets_update_values
    )
    from tools.adk_tools.firestore_adk_tools import (
        add_product,
        query_products,
        add_customer,
        find_customer,
        create_quote,
        add_expense_record,
        query_expenses
    )

    # Create list of tools (ADK-compatible callables)
    tools = [
        # Vision/OCR tools
        extract_receipt_data,
        categorize_expense,
        # Drive tools (for reading receipt images)
        drive_search_files,
        drive_get_file,
        drive_upload_file,
        # Sheets tools (for saving expense data - legacy support)
        sheets_get_values,
        sheets_append_values,
        sheets_update_values,
        # Firestore tools (for database storage)
        add_product,
        query_products,
        add_customer,
        find_customer,
        create_quote,
        add_expense_record,
        query_expenses
    ]

    logger.info(f"Initialized {len(tools)} ADK tools for expense agent")

    # Load instruction from file
    instruction_file = os.path.join(
        os.path.dirname(__file__),
        "..",
        "expense",
        "instructions.md"
    )

    try:
        with open(instruction_file, 'r', encoding='utf-8') as f:
            instruction = f.read()
    except Exception as e:
        logger.warning(f"Failed to load instruction file: {e}")
        instruction = "You are Expense, a receipt processing specialist using Gemini Flash OCR."

    # Inject current datetime context for accurate receipt date handling
    instruction = inject_datetime_context(instruction, user_timezone="Europe/Zagreb")

    # Create agent using factory
    agent = create_adk_agent(
        name="expense",
        model=model,
        description="Receipt processing specialist: OCR extraction from images, expense categorization, saves to Firestore and Sheets",
        tools=tools,
        instruction=instruction,  # Pass instruction content, not file path
        load_instruction_from_file=False,  # We already loaded it manually
        config={
            "temperature": 0.3,  # Consistent data extraction
            "max_tokens": 2048,  # Enough for detailed receipts
        }
    )

    logger.info(f"Expense ADK agent created with {len(tools)} tools")
    logger.info(f"Model: {model}")
    logger.info(f"Flash-First OCR strategy: ~$0.00007 per receipt")
    return agent


# Create singleton instance for easy import
expense_agent = None


def get_expense_agent(
    model: str = "gemini-2.5-flash",
    credentials=None
) -> LlmAgent:
    """
    Get or create singleton Expense agent instance.

    Args:
        model: Gemini model
        credentials: Optional OAuth2 credentials

    Returns:
        LlmAgent instance
    """
    global expense_agent

    if expense_agent is None:
        expense_agent = create_expense_agent(
            model=model,
            credentials=credentials
        )

    return expense_agent


if __name__ == "__main__":
    # Test agent creation
    import asyncio

    async def test():
        agent = create_expense_agent()
        print(f"[OK] Expense ADK agent created: {agent.name}")
        print(f"   Model: {agent.model}")
        print(f"   Description: {agent.description}")
        print(f"   Tools: {len(agent.tools)}")
        print(f"   Instruction preview: {agent.instruction[:200]}...")

        # Display available tools
        print(f"\n[TOOLS] Available Tools:")
        for tool in agent.tools:
            tool_name = getattr(tool, '__name__', str(tool))
            print(f"   - {tool_name}")

        print(f"\n[CAPABILITIES] Receipt Processing Operations:")
        print("   - Multimodal OCR with Gemini Flash")
        print("   - Structured data extraction (Pydantic schema)")
        print("   - Automatic expense categorization")
        print("   - Confidence-based validation")
        print("   - Google Sheets integration")
        print("   - Drive folder monitoring")

        print(f"\n[COST] Flash-First Strategy:")
        print("   - ~$0.00007 per receipt")
        print("   - 1400x cheaper than Document AI")
        print("   - 500 receipts/month = ~$0.035")

    asyncio.run(test())
