"""
Integration Test for Mailer ADK Agent

Tests the native ADK Mailer agent using Runner and real Gmail API.
This verifies that the ADK migration is working correctly.
"""

import pytest
import asyncio
import os
import sys
import logging
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Load environment
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@pytest.fixture
def mailer_agent():
    """Create Mailer ADK agent"""
    from agents.adk_agents.mailer_adk import create_mailer_agent

    agent = create_mailer_agent(model="gemini-2.5-flash")
    return agent


@pytest.fixture
def runner(mailer_agent):
    """Create ADK Runner with Mailer agent"""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    session_service = InMemorySessionService()
    runner = Runner(
        agent=mailer_agent,
        app_name="agents",  # Must match directory structure
        session_service=session_service
    )

    # Store session_service for session creation
    runner.session_service = session_service
    return runner


async def run_agent_helper(runner, user_message: str, session_id: str, user_id: str = "test-user"):
    """Helper to run agent with correct API"""
    from google.genai import types

    # Create session if it doesn't exist
    try:
        session = await runner.session_service.create_session(
            app_name="agents",
            user_id=user_id,
            session_id=session_id
        )
    except Exception:
        # Session might already exist
        pass

    # Create Content
    content = types.Content(
        role="user",
        parts=[types.Part(text=user_message)]
    )

    # Run agent
    events = runner.run_async(
        new_message=content,
        session_id=session_id,
        user_id=user_id
    )

    # Collect response
    response_text = ""
    async for event in events:
        if hasattr(event, 'text'):
            response_text += event.text
        elif hasattr(event, 'content'):
            if hasattr(event.content, 'parts'):
                for part in event.content.parts:
                    if hasattr(part, 'text'):
                        response_text += part.text

    return response_text


@pytest.mark.asyncio
@pytest.mark.integration
async def test_mailer_agent_creation():
    """Test that Mailer ADK agent can be created"""
    from agents.adk_agents.mailer_adk import create_mailer_agent

    agent = create_mailer_agent()

    assert agent is not None
    assert agent.name == "mailer"
    assert agent.model == "gemini-2.5-flash"
    assert len(agent.tools) > 0  # Should have Gmail tools
    assert agent.instruction is not None
    assert "Gmail" in agent.instruction or "email" in agent.instruction.lower()

    logger.info(f"✅ Mailer agent created: {agent.name}")
    logger.info(f"   Tools: {len(agent.tools)}")
    logger.info(f"   Model: {agent.model}")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_runner_creation(runner, mailer_agent):
    """Test that Runner can be created with Mailer agent"""
    assert runner is not None
    assert runner.agent == mailer_agent

    logger.info("✅ Runner created with Mailer agent")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN"),
    reason="No OAuth token - run: python tools/oauth_cli.py --auth"
)
async def test_search_emails_with_runner(runner):
    """Test searching emails using Runner"""
    logger.info("\n" + "="*80)
    logger.info("TEST: Search Emails with ADK Runner")
    logger.info("="*80)

    # Search for recent emails
    response_text = await run_agent_helper(
        runner,
        "Search for the 5 most recent emails",
        session_id="test-search-001"
    )

    logger.info(f"\n📧 Search Results:\n{response_text}")

    # Verify response
    assert response_text is not None
    assert len(response_text) > 0

    # Should mention threads or emails
    assert any(word in response_text.lower() for word in ['email', 'thread', 'message', 'inbox'])

    logger.info("✅ Email search successful")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN"),
    reason="No OAuth token - run: python tools/oauth_cli.py --auth"
)
async def test_send_email_with_runner(runner):
    """Test sending email using Runner (creates draft to avoid spam)"""
    logger.info("\n" + "="*80)
    logger.info("TEST: Create Email Draft with ADK Runner")
    logger.info("="*80)

    # Get test email from environment or use default
    test_email = os.getenv("TEST_EMAIL", "test@example.com")

    # Create a draft (safer than sending)
    response_text = await run_agent_helper(
        runner,
        f"Create a draft email to {test_email} with subject 'ADK Test' and body 'Testing ADK Mailer agent'",
        session_id="test-draft-001"
    )

    logger.info(f"\n📝 Draft Creation Result:\n{response_text}")

    # Verify response
    assert response_text is not None
    assert len(response_text) > 0

    # Should mention draft creation
    assert any(word in response_text.lower() for word in ['draft', 'created', 'saved'])

    logger.info("✅ Email draft creation successful")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN"),
    reason="No OAuth token - run: python tools/oauth_cli.py --auth"
)
async def test_list_labels_with_runner(runner):
    """Test listing Gmail labels using Runner"""
    logger.info("\n" + "="*80)
    logger.info("TEST: List Gmail Labels with ADK Runner")
    logger.info("="*80)

    response_text = await run_agent_helper(
        runner,
        "List all my Gmail labels",
        session_id="test-labels-001"
    )

    logger.info(f"\n🏷️  Labels Result:\n{response_text}")

    # Verify response
    assert response_text is not None
    assert len(response_text) > 0

    # Should mention common labels
    # Note: Some might be in Croatian ("Ulazna pošta" for INBOX)
    assert any(word in response_text.lower() for word in ['label', 'inbox', 'ulazna', 'sent', 'poslano'])

    logger.info("✅ List labels successful")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_session_persistence(runner):
    """Test that session state persists across multiple calls"""
    logger.info("\n" + "="*80)
    logger.info("TEST: Session State Persistence")
    logger.info("="*80)

    session_id = "test-persistence-001"

    # First call
    response1_text = await run_agent_helper(
        runner,
        "Remember that my favorite email client is Gmail",
        session_id=session_id
    )

    logger.info(f"\n💬 First Response:\n{response1_text}")

    # Second call - should remember context (same session_id!)
    response2_text = await run_agent_helper(
        runner,
        "What did I just tell you about my favorite email client?",
        session_id=session_id
    )

    logger.info(f"\n💬 Second Response:\n{response2_text}")

    # Verify that context was maintained
    assert response2_text is not None
    assert "gmail" in response2_text.lower()

    logger.info("✅ Session persistence working")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_error_handling(runner):
    """Test error handling when invalid request is made"""
    logger.info("\n" + "="*80)
    logger.info("TEST: Error Handling")
    logger.info("="*80)

    # Try to send email without proper recipient
    response_text = await run_agent_helper(
        runner,
        "Send email to nobody with no subject",
        session_id="test-error-001"
    )

    logger.info(f"\n⚠️  Error Response:\n{response_text}")

    # Should handle gracefully, not crash
    assert response_text is not None

    logger.info("✅ Error handling working")


if __name__ == "__main__":
    """Run tests manually"""
    print("\n" + "="*80)
    print("MAILER ADK AGENT - INTEGRATION TESTS")
    print("="*80)

    # Check authentication
    if not os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN"):
        print("\nWARNING: No OAuth token found!")
        print("   Please authenticate: python tools/oauth_cli.py --auth")
        print("\n   Running only basic tests...\n")

    # Run tests
    asyncio.run(test_mailer_agent_creation())

    if os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN"):
        print("\nRunning Gmail API tests...\n")

        from agents.adk_agents.mailer_adk import create_mailer_agent
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService

        agent = create_mailer_agent()
        runner = Runner(
            agent=agent,
            app_name="test_mailer_adk",
            session_service=InMemorySessionService()
        )

        asyncio.run(test_runner_creation(runner, agent))
        asyncio.run(test_search_emails_with_runner(runner))
        asyncio.run(test_list_labels_with_runner(runner))
        asyncio.run(test_send_email_with_runner(runner))
        asyncio.run(test_session_persistence(runner))
        asyncio.run(test_error_handling(runner))

    print("\n" + "="*80)
    print("ALL TESTS COMPLETED")
    print("="*80)
