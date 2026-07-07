"""
Skladištar ADK Agent

Voice-first warehouse (skladište) specialist. Handles stock queries,
stock adjustments and new product creation through the ERP service layer,
with a mandatory spoken-confirmation protocol before any write.

Kept deliberately small (4 ERP tools, Flash model, low temperature) so the
voice lane stays fast — unlike analyst, which carries the full Sheets belt
on the pro tier.
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
from config.deployment_config import is_erp_enabled

logger = logging.getLogger(__name__)


def create_skladistar_agent(
    model: str = "gemini-3.5-flash",
    credentials=None
) -> LlmAgent:
    """
    Create Skladištar ADK agent for warehouse voice operations.

    Tools (only when ERP is enabled for the deployment profile):
    - erp_find_product: fuzzy product resolution (STT-friendly)
    - erp_get_stock_levels: stock overview / low-stock report
    - erp_adjust_stock: confirmed stock add/remove (delta)
    - erp_create_product: confirmed new product creation

    Args:
        model: Gemini model to use (default: "gemini-3.5-flash")
        credentials: Unused; present for factory signature compatibility.

    Returns:
        LlmAgent instance configured for warehouse operations
    """
    all_tools = []
    description = (
        "Warehouse (skladište) voice specialist: stock queries, stock "
        "adjustments and new product creation with spoken confirmation. "
        "Keywords: skladište, zaliha, zalihe, artikl, inventura, lager, "
        "dodaj na stanje, skini sa stanja, koliko imam."
    )

    if is_erp_enabled():
        from tools.adk_tools.erp_adk_tools import (
            erp_find_product,
            erp_get_stock_levels,
            erp_adjust_stock,
            erp_create_product,
        )
        all_tools = [
            erp_find_product,
            erp_get_stock_levels,
            erp_adjust_stock,
            erp_create_product,
        ]
    else:
        logger.warning(
            "Skladistar agent created without ERP tools (ERP disabled for this profile)"
        )

    agent = create_adk_agent(
        name="skladistar",
        model=model,
        description=description,
        tools=all_tools,
        load_instruction_from_file=True,  # agents/skladistar/instructions.md
        config={
            "temperature": 0.2,  # Low temperature: write discipline over creativity
            "max_tokens": 1024,
        }
    )

    logger.info(f"Skladistar ADK agent created with {len(all_tools)} tools")
    return agent


# Create singleton instance for easy import
skladistar_agent = None


def get_skladistar_agent(
    model: str = "gemini-3.5-flash",
    credentials=None
) -> LlmAgent:
    """Get or create singleton Skladistar agent instance."""
    global skladistar_agent

    if skladistar_agent is None:
        skladistar_agent = create_skladistar_agent(
            model=model,
            credentials=credentials
        )

    return skladistar_agent


if __name__ == "__main__":
    agent = create_skladistar_agent()
    print(f"[OK] Skladistar ADK agent created: {agent.name}")
    print(f"   Model: {agent.model}")
    print(f"   Tools: {len(agent.tools)}")
    for tool in agent.tools:
        print(f"   - {getattr(tool, '__name__', str(tool))}")
