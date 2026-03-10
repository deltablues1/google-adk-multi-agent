"""
Mailer ADK Agent - Gmail Specialist

Native Google ADK implementation using LlmAgent.
Uses Gmail ADK tools for Gmail API operations.
"""

import logging
import os
from agents.adk_agents.adk_agent_factory import create_adk_agent
from agents.adk_agents.datetime_context import inject_datetime_context

logger = logging.getLogger(__name__)


def create_mailer_agent(
    model: str = "gemini-2.5-flash",
    user_timezone: str = "Europe/Zagreb"
):
    """
    Create Mailer ADK agent for Gmail operations.

    Mailer is a specialized agent for managing Gmail:
    - Send and reply to emails
    - Search and read threads
    - Create drafts
    - Manage labels
    - Professional email composition
    - Date-aware meeting confirmations

    Args:
        model: Gemini model to use (default: gemini-2.5-flash)
        user_timezone: User's timezone for date awareness (default: "Europe/Zagreb")

    Returns:
        LlmAgent configured for Gmail operations
    """
    # Load instruction from markdown file
    instruction_path = os.path.join(
        os.path.dirname(__file__), "..", "mailer", "instructions.md"
    )

    with open(instruction_path, "r", encoding="utf-8") as f:
        instruction = f.read()

    # Inject current datetime and timezone context (uses centralized helper)
    instruction = inject_datetime_context(instruction, user_timezone)

    # Import Gmail ADK tools
    from tools.adk_tools.gmail_adk_tools import (
        gmail_search_threads,
        gmail_get_thread,
        gmail_send_message,
        gmail_create_draft,
        gmail_modify_thread,
        gmail_list_labels
    )

    # Create list of tools
    tools = [
        gmail_search_threads,
        gmail_get_thread,
        gmail_send_message,
        gmail_create_draft,
        gmail_modify_thread,
        gmail_list_labels
    ]

    # Create agent using factory
    agent = create_adk_agent(
        name="mailer",
        model=model,
        description="Gmail specialist: sending, reading, and managing emails",
        tools=tools,
        instruction=instruction,
        config={
            "temperature": 0.7,  # Higher for natural email composition
            "max_tokens": 2048,
        }
    )

    logger.info(f"Mailer agent created with {len(tools)} tools")
    return agent


# For backward compatibility and testing
if __name__ == "__main__":
    agent = create_mailer_agent()
    print(f"Mailer agent created: {agent.name}")
    print(f"Tools: {len(agent._tools)}")
