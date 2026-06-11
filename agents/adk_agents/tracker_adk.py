"""
Tracker ADK Agent - Google Tasks Specialist

Native Google ADK implementation using LlmAgent.
Uses Tasks ADK tools for Google Tasks API operations.
"""

import logging
import os
from agents.adk_agents.adk_agent_factory import create_adk_agent
from agents.adk_agents.datetime_context import inject_datetime_context
from config.deployment_config import is_erp_enabled

logger = logging.getLogger(__name__)


def create_tracker_agent(
    model: str = "gemini-3.5-flash",
    user_timezone: str = "Europe/Zagreb"
):
    """
    Create Tracker ADK agent for Google Tasks management.

    Tracker is a specialized agent for managing Google Tasks:
    - List task lists and tasks
    - Create new tasks with due dates and notes
    - Update tasks (modify details, mark as complete)
    - Delete tasks
    - Organize tasks into lists

    Args:
        model: Gemini model to use (default: gemini-2.5-flash)
        user_timezone: User's timezone for date awareness (default: "Europe/Zagreb")

    Returns:
        LlmAgent configured for task management
    """
    # Load instruction from markdown file
    instruction_path = os.path.join(
        os.path.dirname(__file__), "..", "tracker", "instructions.md"
    )

    with open(instruction_path, "r", encoding="utf-8") as f:
        instruction = f.read()

    # Inject current datetime context for accurate due date handling
    instruction = inject_datetime_context(instruction, user_timezone)

    # Import Tasks ADK tools
    from tools.adk_tools.tasks_adk_tools import (
        tasks_list_task_lists,
        tasks_list_tasks,
        tasks_create_task,
        tasks_update_task,
        tasks_delete_task,
        tasks_complete_task
    )

    # Create list of tools
    tools = [
        tasks_list_task_lists,
        tasks_list_tasks,
        tasks_create_task,
        tasks_update_task,
        tasks_delete_task,
        tasks_complete_task,
    ]
    description = "Google Tasks specialist for task and task-list management"

    if is_erp_enabled():
        from tools.adk_tools.erp_adk_tools import (
            erp_list_open_invoices,
            erp_record_payment,
            erp_get_open_payables,
            erp_get_activity_feed,
            erp_get_inventory_movements,
            erp_list_quotes,
            erp_get_quote,
        )
        tools.extend([
            erp_list_open_invoices,
            erp_record_payment,
            erp_get_open_payables,
            erp_get_activity_feed,
            erp_get_inventory_movements,
            erp_list_quotes,
            erp_get_quote,
        ])
        description += ", plus ERP payment and activity tracking"

    # ERP tools — only on full deployment
    from config.deployment_config import ENABLE_ERP
    if ENABLE_ERP:
        from tools.adk_tools.erp_adk_tools import (
            erp_list_open_invoices,
            erp_record_payment,
            erp_get_open_payables,
            erp_get_activity_feed,
            erp_get_inventory_movements,
            erp_list_quotes,
            erp_get_quote,
        )
        tools.extend([
            erp_list_open_invoices,
            erp_record_payment,
            erp_get_open_payables,
            erp_get_activity_feed,
            erp_get_inventory_movements,
            erp_list_quotes,
            erp_get_quote,
        ])

    # Create agent using factory
    agent = create_adk_agent(
        name="tracker",
        model=model,
        description=description,
        tools=tools,
        instruction=instruction,
        config={
            "temperature": 0.3,  # Slightly higher for natural task organization
            "max_tokens": 1024,
        }
    )

    logger.info(f"Tracker agent created with {len(tools)} tools")
    return agent


# For backward compatibility and testing
if __name__ == "__main__":
    agent = create_tracker_agent()
    print(f"Tracker agent created: {agent.name}")
    print(f"Tools: {len(agent._tools)}")
