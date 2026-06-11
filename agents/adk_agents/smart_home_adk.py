"""
Smart Home ADK Agent - MQTT pametna kuća

Upravljanje svjetlima, utičnicama i dimmerom preko ESP32-IO MQTT brokera.
"""

import os
import logging

from agents.adk_agents.adk_agent_factory import create_adk_agent
from agents.adk_agents.datetime_context import inject_datetime_context

logger = logging.getLogger(__name__)


def create_smart_home_agent(
    model: str = "gemini-3.5-flash",
    user_timezone: str = "Europe/Zagreb"
):
    """Create Smart Home ADK agent for MQTT control"""

    # Load instructions
    instruction_path = os.path.join(
        os.path.dirname(__file__), "..", "smart_home", "instructions.md"
    )
    with open(instruction_path, "r", encoding="utf-8") as f:
        instruction = f.read()

    instruction = inject_datetime_context(instruction, user_timezone)

    # Import tools
    from tools.adk_tools.mqtt_adk_tools import get_mqtt_adk_tools
    tools = get_mqtt_adk_tools()

    agent = create_adk_agent(
        name="smart_home",
        model=model,
        description="Smart home MQTT specialist: lights, outlets, dimmer, scenes",
        tools=tools,
        instruction=instruction,
        load_instruction_from_file=False,
        config={
            "temperature": 0.3,
            "max_tokens": 1536,
        }
    )

    logger.info("Smart Home ADK agent created")
    return agent
