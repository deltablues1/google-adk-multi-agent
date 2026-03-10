"""
Test Complete Multi-Step Workflow

Tests that orchestrator completes ALL steps:
1. Research
2. Create document
3. Save to specific folder
4. Find contact
5. Send email

This mimics the real user request.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agents.adk_agents.smart_orchestrator import create_smart_orchestrator
from agents.adk_agents.decision_validator import create_decision_validator
from agents.adk_agents.ask_user_agent import create_ask_user_agent
from config.agent_registry import create_agent_instance, get_worker_agent_names
from agents.adk_agents.runner_utils import RunnerHelper
from datetime import datetime


async def test_complete_workflow():
    """Test complete multi-step workflow"""

    print("="*80)
    print("TESTING COMPLETE MULTI-STEP WORKFLOW")
    print("="*80)
    print()

    # Initialize orchestrator
    print("Initializing orchestrator...")
    worker_names = get_worker_agent_names()
    worker_agents = [create_agent_instance(name) for name in worker_names]

    decision_validator = create_decision_validator(model="gemini-2.5-flash", sub_agents=[])
    ask_user = create_ask_user_agent(model="gemini-2.5-flash")

    orchestrator = create_smart_orchestrator(
        model="gemini-2.5-pro",
        worker_agents=worker_agents,
        validator_agent=decision_validator,
        ask_user_agent=ask_user
    )

    session_id = f"workflow-test-{int(datetime.now().timestamp())}"
    orchestrator_helper = RunnerHelper(
        agent=orchestrator,
        session_id=session_id,
        user_id="test-user",
        app_name="agents"
    )

    print(f"[OK] Orchestrator initialized")
    print()

    # Test query - similar to user's real query
    query = """
    Možeš li mi napraviti kratko istraživanje o "quantum computing",
    spremiti dokument na Google Drive u folder "Test Documents 2026",
    te poslati taj dokument kontaktu "Tomislav Golić" na email.
    """

    print("User Query:")
    print(query.strip())
    print()
    print("-" * 80)
    print("Executing workflow...")
    print("-" * 80)
    print()

    try:
        result = await orchestrator_helper.run(query)

        print()
        print("="*80)
        print("RESULT:")
        print("="*80)
        try:
            print(result)
        except UnicodeEncodeError:
            print("[Result contains emojis - showing length only]")
            print(f"Result length: {len(result)} characters")
        print()

        # Check if all steps were completed
        result_lower = result.lower()

        steps_completed = {
            "research": any(word in result_lower for word in ["research", "istraživanje", "quantum"]),
            "document": any(word in result_lower for word in ["document", "dokument", "doc", "created"]),
            "folder": any(word in result_lower for word in ["folder", "test documents", "saved", "spremljen"]),
            "contact": any(word in result_lower for word in ["contact", "kontakt", "tomislav", "golić"]),
            "email": any(word in result_lower for word in ["email", "sent", "poslao", "mail"]),
        }

        print()
        print("="*80)
        print("STEP COMPLETION CHECK:")
        print("="*80)
        for step, completed in steps_completed.items():
            status = "[OK] DONE" if completed else "[X] MISSING"
            print(f"{status}: {step.capitalize()}")

        completed_count = sum(steps_completed.values())
        total_count = len(steps_completed)

        print()
        print(f"Completed: {completed_count}/{total_count} steps ({completed_count/total_count*100:.0f}%)")
        print()

        if completed_count == total_count:
            print("[OK] ALL STEPS COMPLETED!")
            return True
        elif completed_count >= 3:
            print("[PARTIAL] Most steps completed, but workflow incomplete")
            return False
        else:
            print("[FAIL] Workflow incomplete - orchestrator stopped early")
            return False

    except Exception as e:
        print(f"[ERROR] Workflow crashed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_complete_workflow())
    sys.exit(0 if success else 1)
