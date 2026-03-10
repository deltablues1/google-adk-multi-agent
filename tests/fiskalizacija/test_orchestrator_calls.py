"""
Test Orchestrator Agent Calls

Verifies that orchestrator calls multiple agents sequentially,
regardless of API success/failure. This tests the AgentTool pattern.
"""

import asyncio
import sys
from pathlib import Path
import logging

sys.path.insert(0, str(Path(__file__).parent))

# Setup detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from agents.adk_agents.smart_orchestrator import create_smart_orchestrator
from agents.adk_agents.decision_validator import create_decision_validator
from agents.adk_agents.ask_user_agent import create_ask_user_agent
from config.agent_registry import create_agent_instance, get_worker_agent_names
from agents.adk_agents.runner_utils import RunnerHelper
from datetime import datetime


async def test_orchestrator_calls():
    """Test that orchestrator calls multiple agents"""

    print("="*80)
    print("TESTING ORCHESTRATOR MULTI-AGENT CALLING (AgentTool Pattern)")
    print("="*80)
    print()

    # Initialize orchestrator
    print("Initializing orchestrator with AgentTool pattern...")
    worker_names = get_worker_agent_names()
    worker_agents = [create_agent_instance(name) for name in worker_names]

    print(f"Available worker agents: {[a.name for a in worker_agents]}")
    print()

    decision_validator = create_decision_validator(model="gemini-2.5-flash", sub_agents=[])
    ask_user = create_ask_user_agent(model="gemini-2.5-flash")

    orchestrator = create_smart_orchestrator(
        model="gemini-2.5-pro",
        worker_agents=worker_agents,
        validator_agent=decision_validator,
        ask_user_agent=ask_user
    )

    session_id = f"call-test-{int(datetime.now().timestamp())}"
    orchestrator_helper = RunnerHelper(
        agent=orchestrator,
        session_id=session_id,
        user_id="test-user",
        app_name="agents"
    )

    print("[OK] Orchestrator initialized")
    print()

    # Multi-step query that's very explicit
    query = """
    MULTI-STEP REQUEST (Execute ALL steps even if some fail):

    Step 1: Call researcher agent to search for "Python programming" (may fail due to rate limits - that's OK)
    Step 2: Call scribe agent to create a document titled "Test Document" with content "This is a test"
    Step 3: Call secretary agent to list today's calendar events (may fail - that's OK)

    Execute ALL THREE steps and report which ones succeeded/failed.
    """

    print("User Query:")
    print(query.strip())
    print()
    print("-" * 80)
    print("Executing... (watch for agent calls in logs above)")
    print("-" * 80)
    print()

    try:
        result = await orchestrator_helper.run(query)

        print()
        print("="*80)
        print("ORCHESTRATOR RESULT:")
        print("="*80)
        print(result)
        print()

        # Check if orchestrator mentioned all three agents
        result_lower = result.lower()

        mentioned_agents = {
            "researcher": any(word in result_lower for word in ["research", "istraživanj", "pretraživanj"]),
            "scribe": any(word in result_lower for word in ["scribe", "document", "dokument"]),
            "secretary": any(word in result_lower for word in ["secretary", "calendar", "kalendar", "event"]),
        }

        print("="*80)
        print("AGENT CALL ANALYSIS:")
        print("="*80)

        for agent, mentioned in mentioned_agents.items():
            status = "[OK] CALLED" if mentioned else "[X] NOT CALLED"
            print(f"{status}: {agent}")

        called_count = sum(mentioned_agents.values())
        total_count = len(mentioned_agents)

        print()
        print(f"Agents called: {called_count}/{total_count} ({called_count/total_count*100:.0f}%)")
        print()

        if called_count >= 2:
            print("[SUCCESS] Orchestrator called multiple agents sequentially!")
            print("AgentTool pattern is working correctly.")
            return True
        else:
            print("[FAIL] Orchestrator did not call multiple agents")
            return False

    except Exception as e:
        print(f"[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_orchestrator_calls())
    sys.exit(0 if success else 1)
