"""
Expense ADK Agent

Native ADK implementation of receipt processing specialist using LlmAgent primitive.
Uses Gemini Flash multimodal OCR for cost-effective expense tracking.
"""

from typing import Optional
import logging
import sys
import os

if __name__ == "__main__":
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
    from dotenv import load_dotenv

    load_dotenv()

from google.adk.agents import LlmAgent

from agents.adk_agents.adk_agent_factory import create_adk_agent
from config.deployment_config import is_erp_enabled

logger = logging.getLogger(__name__)


def create_expense_agent(
    model: str = "gemini-3.5-flash",
    credentials=None,
) -> LlmAgent:
    """
    Create Expense ADK agent for receipt processing operations.
    """
    from tools.adk_tools.vision_adk_tools import (
        extract_receipt_data,
        categorize_expense,
        monitor_drive_invoices,
    )
    from tools.adk_tools.drive_adk_tools import (
        drive_search_files,
        drive_get_file,
        drive_upload_file,
    )
    from tools.adk_tools.sheets_adk_tools import (
        sheets_get_values,
        sheets_append_values,
        sheets_update_values,
    )
    from tools.adk_tools.firestore_adk_tools import (
        add_product,
        query_products,
        add_customer,
        find_customer,
        create_quote,
        add_expense_record,
        query_expenses,
    )

    tools = [
        extract_receipt_data,
        categorize_expense,
        drive_search_files,
        drive_get_file,
        drive_upload_file,
        sheets_get_values,
        sheets_append_values,
        sheets_update_values,
        add_product,
        query_products,
        add_customer,
        find_customer,
        create_quote,
        add_expense_record,
        query_expenses,
        monitor_drive_invoices,
    ]

    if is_erp_enabled():
        from tools.adk_tools.erp_adk_tools import (
            erp_create_vendor_invoice_from_ocr,
            erp_get_vendor_invoice,
        )

        tools.extend([
            erp_create_vendor_invoice_from_ocr,
            erp_get_vendor_invoice,
        ])

    logger.info(f"Initialized {len(tools)} ADK tools for expense agent")

    instruction_file = os.path.join(
        os.path.dirname(__file__),
        "..",
        "expense",
        "instructions.md",
    )

    try:
        with open(instruction_file, "r", encoding="utf-8") as f:
            instruction = f.read()
    except Exception as e:
        logger.warning(f"Failed to load instruction file: {e}")
        instruction = "You are Expense, a receipt processing specialist using Gemini Flash OCR."

    if not is_erp_enabled():
        instruction += (
            "\n\nDeployment constraint: ERP is disabled in this environment. "
            "Do not promise ERP drafts, ERP UI review steps, or vendor invoice creation. "
            "Use OCR, Drive, Firestore, and Sheets flows only."
        )

    # Datum/vrijeme se NE ubacuje ovdje: to bi zamrznulo sat na trenutak
    # kad je agent stvoren. Predaje se predložak, a tvornica ga omota u
    # ADK instruction provider koji ga renderira pri svakom pozivu.

    agent = create_adk_agent(
        name="expense",
        model=model,
        description="Receipt processing specialist: OCR extraction from images, expense categorization, saves to Firestore and Sheets",
        tools=tools,
        instruction=instruction,
        load_instruction_from_file=False,
        config={
            "temperature": 0.3,
            "max_tokens": 2048,
        },
    )

    logger.info(f"Expense ADK agent created with {len(tools)} tools")
    logger.info(f"Model: {model}")
    logger.info("Flash-First OCR strategy: ~$0.00007 per receipt")
    return agent


expense_agent = None


def get_expense_agent(
    model: str = "gemini-3.5-flash",
    credentials=None,
) -> LlmAgent:
    global expense_agent

    if expense_agent is None:
        expense_agent = create_expense_agent(
            model=model,
            credentials=credentials,
        )

    return expense_agent


if __name__ == "__main__":
    import asyncio

    async def test():
        agent = create_expense_agent()
        print(f"[OK] Expense ADK agent created: {agent.name}")
        print(f"   Model: {agent.model}")
        print(f"   Description: {agent.description}")
        print(f"   Tools: {len(agent.tools)}")
        print(f"   Instruction preview: {agent.instruction[:200]}...")

        print("\n[TOOLS] Available Tools:")
        for tool in agent.tools:
            tool_name = getattr(tool, "__name__", str(tool))
            print(f"   - {tool_name}")

    asyncio.run(test())
