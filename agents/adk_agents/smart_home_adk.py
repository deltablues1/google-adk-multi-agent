"""
Smart Home ADK Agent - MQTT pametna kuća

Upravljanje svjetlima, utičnicama i dimmerom preko ESP32-IO MQTT brokera.
"""

import os
import logging

from agents.adk_agents.adk_agent_factory import create_adk_agent

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

    # Datum/vrijeme se NE ubacuje ovdje: to bi zamrznulo sat na trenutak
    # kad je agent stvoren. Predaje se predložak, a tvornica ga omota u
    # ADK instruction provider koji ga renderira pri svakom pozivu.

    # Import tools
    from tools.adk_tools.mqtt_adk_tools import get_mqtt_adk_tools
    tools = get_mqtt_adk_tools()

    # TV / media tools preko Home Assistant REST API-ja (opt-in: aktivno samo
    # kad su HA_URL i HA_TOKEN postavljeni u .env).
    if os.getenv("HA_URL", "").strip() and os.getenv("HA_TOKEN", "").strip():
        from tools.adk_tools.ha_adk_tools import get_ha_adk_tools
        from tools.adk_tools.ha_sensor_tools import get_ha_sensor_tools
        # Sklopke idu preko MQTT-a, ali mjerenja (temperatura, vlaga, tlak,
        # kvaliteta zraka, potrošnja) postoje samo u HA — bez ovih read-only
        # alata agent ih nema odakle pročitati.
        tools = tools + get_ha_adk_tools() + get_ha_sensor_tools()
        logger.info("Smart Home agent: Home Assistant TV + sensor tools enabled")

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
