"""
Christian Guide ADK Agent

Reflective Christian / spiritual guide with optional Vertex AI RAG corpus.
"""

import logging
import os

from google.adk.agents import LlmAgent

logger = logging.getLogger(__name__)


def create_christian_guide_agent(
    model: str = "gemini-3-flash-preview",
    credentials=None,
) -> LlmAgent:
    """
    Create a Christian guide agent for reflective dialogue, discernment,
    doctrine-aware explanations, and guided spiritual exercises.
    """
    from tools.christian_tools import get_christian_rag_tool

    rag_tool = get_christian_rag_tool()
    tools = [rag_tool] if rag_tool is not None else []

    instruction_path = os.path.join(
        os.path.dirname(__file__), "..", "christian_guide", "instructions.md"
    )
    with open(instruction_path, "r", encoding="utf-8") as handle:
        instruction = handle.read()

    if rag_tool is not None:
        instruction += (
            "\nKoristi ChristianKnowledgeBase kad korisnik pita o Bibliji, "
            "krscanskom nauku, duhovnim klasicima, razlucivanju, molitvi ili "
            "duhovnim vjezbama. Kada koristis bazu znanja, oslanjaj se na "
            "izvore, ali odgovori formuliraj prirodno i razgovorno."
        )

    agent = LlmAgent(
        name="christian_guide",
        model=model or "gemini-3-flash-preview",
        tools=tools,
        instruction=instruction,
        description=(
            "Christian spiritual guide for doctrine-aware explanations, "
            "reflection, discernment, prayer, and guided exercises"
        ),
    )
    logger.info(
        "christian_guide agent created (model=%s, RAG=%s)",
        model,
        "yes" if rag_tool else "no",
    )
    return agent


christian_guide_agent = None


def get_christian_guide_agent(
    model: str = "gemini-3-flash-preview",
    credentials=None,
) -> LlmAgent:
    """Get or create singleton christian_guide agent instance."""
    global christian_guide_agent

    if christian_guide_agent is None:
        christian_guide_agent = create_christian_guide_agent(
            model=model,
            credentials=credentials,
        )

    return christian_guide_agent
