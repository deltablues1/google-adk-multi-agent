"""
Marketing ADK Agent

Native ADK implementation of Google Ads specialist with Vertex AI visual generation.
Uses Gemini Flash for creative ideation and Vertex AI for asset generation.

Capabilities:
- Visual asset generation (images and videos) with Vertex AI Imagen/Veo
- YouTube video hosting for video ads
- Google Ads campaign creation (PAUSED status by default)
- Human-in-the-loop workflow for asset approval
- Professional ad copy and creative direction

Usage:
    from agents.adk_agents.marketing_adk import create_marketing_agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    # Create agent
    marketing = create_marketing_agent()

    # Create runner
    runner = Runner(
        agent=marketing,
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

logger = logging.getLogger(__name__)


def create_marketing_agent(
    model: str = "gemini-3.5-flash",
    credentials=None
) -> LlmAgent:
    """
    Create Marketing ADK agent for Google Ads and visual content generation.

    This agent specializes in:
    - Visual asset generation (Vertex AI Imagen for images, Veo for videos)
    - YouTube video hosting for ad campaigns
    - Google Ads campaign creation (PAUSED by default - safe)
    - Human-in-the-loop approval workflow
    - Creative direction and ad copy optimization

    Safety & Budget Protection:
    - NEVER creates campaigns without user approval
    - ALWAYS shows generated assets for review first
    - Campaigns start in PAUSED state (no spend until user activates)
    - Explicit confirmation required before proceeding

    Args:
        model: Gemini model to use (default: "gemini-3.5-flash" for creative ideation)
        credentials: Optional OAuth2 credentials. If None, uses token file.

    Returns:
        LlmAgent instance configured for marketing operations

    Example:
        >>> marketing = create_marketing_agent()
        >>> runner = Runner(agent=marketing, app_name="agents", session_service=InMemorySessionService())
        >>> # Use runner_utils for simplified execution
        >>> from agents.adk_agents.runner_utils import run_agent_simple
        >>> response = await run_agent_simple(
        ...     marketing,
        ...     "Create an ad campaign for summer sale with product images"
        ... )
    """

    # Import ADK tools (individual callables)
    from tools.adk_tools.marketing_adk_tools import (
        generate_visual_asset,
        upload_to_youtube,
        create_google_ad_draft
    )

    # Create list of tools (ADK-compatible callables)
    tools = [
        # Vertex AI visual generation
        generate_visual_asset,
        # YouTube hosting
        upload_to_youtube,
        # Google Ads campaign creation
        create_google_ad_draft
    ]

    logger.info(f"Initialized {len(tools)} ADK tools for marketing agent")

    # Load instruction from file
    instruction_file = os.path.join(
        os.path.dirname(__file__),
        "..",
        "marketing",
        "instructions.md"
    )

    try:
        with open(instruction_file, 'r', encoding='utf-8') as f:
            instruction = f.read()
    except Exception as e:
        logger.warning(f"Failed to load instruction file: {e}")
        instruction = "You are Marketing, a Google Ads specialist with visual content generation capabilities."

    # Create agent using factory
    agent = create_adk_agent(
        name="marketing",
        model=model,
        description="Google Ads and visual content specialist: generates images/videos with Vertex AI, creates ad campaigns (PAUSED by default), requires user approval",
        tools=tools,
        instruction=instruction,
        load_instruction_from_file=False,  # We already loaded it
        config={
            "temperature": 0.8,  # Higher creativity for ad copy and visual concepts
            "max_tokens": 2048,
        }
    )

    logger.info(f"Marketing ADK agent created with {len(tools)} tools")
    logger.info(f"Model: {model}")
    logger.info(f"Safety: Human-in-the-loop workflow enforced")
    return agent


# Create singleton instance for easy import
marketing_agent = None


def get_marketing_agent(
    model: str = "gemini-3.5-flash",
    credentials=None
) -> LlmAgent:
    """
    Get or create singleton Marketing agent instance.

    Args:
        model: Gemini model
        credentials: Optional OAuth2 credentials

    Returns:
        LlmAgent instance
    """
    global marketing_agent

    if marketing_agent is None:
        marketing_agent = create_marketing_agent(
            model=model,
            credentials=credentials
        )

    return marketing_agent


if __name__ == "__main__":
    # Test agent creation
    import asyncio

    async def test():
        agent = create_marketing_agent()
        print(f"[OK] Marketing ADK agent created: {agent.name}")
        print(f"   Model: {agent.model}")
        print(f"   Description: {agent.description}")
        print(f"   Tools: {len(agent.tools)}")
        print(f"   Instruction preview: {agent.instruction[:200]}...")

        # Display available tools
        print(f"\n[TOOLS] Available Marketing Tools:")
        for tool in agent.tools:
            tool_name = getattr(tool, '__name__', str(tool))
            print(f"   - {tool_name}")

        print(f"\n[CAPABILITIES] Marketing Operations:")
        print("   - Visual asset generation (Imagen for images, Veo for videos)")
        print("   - YouTube video hosting for ad campaigns")
        print("   - Google Ads campaign creation (PAUSED by default)")
        print("   - Human-in-the-loop approval workflow")
        print("   - Professional ad copy and creative direction")

        print(f"\n[SAFETY] Budget Protection:")
        print("   - NEVER creates campaigns without user approval")
        print("   - ALWAYS shows generated assets for review first")
        print("   - Campaigns start in PAUSED state")
        print("   - Explicit confirmation required")

        print(f"\n[WORKFLOW] Typical Ad Campaign Creation:")
        print("   1. Understand goal (product, audience, message)")
        print("   2. Propose creative concept")
        print("   3. Generate visual asset (image or video)")
        print("   4. Show asset to user for approval")
        print("   5. If video: Upload to YouTube")
        print("   6. Create campaign draft (PAUSED state)")
        print("   7. Confirm draft ID and next steps")

    asyncio.run(test())
