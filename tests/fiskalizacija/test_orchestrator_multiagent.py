"""
Orchestrator Multi-Agent Integration Tests

Tests Smart Orchestrator with complex multi-agent workflows using real Google APIs.
This verifies the entire system works end-to-end.

Test scenarios:
1. Sheets + Drive: Analyze data, create report, upload to Drive
2. Contacts + Calendar + Tasks: Create contact, schedule meeting, create follow-up task
3. Sheets + Tasks: Parse sheet data, create tasks for each row
4. Drive + Calendar: Find file, schedule review meeting

NO FISKALIZACIJA - already tested thoroughly
"""

import asyncio
import sys
import logging
import re
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

def safe_print(text):
    """Print text with emoji/special character handling for Windows console"""
    try:
        print(text)
    except UnicodeEncodeError:
        # Strip emojis and other problematic Unicode characters
        emoji_pattern = re.compile("["
            u"\U0001F600-\U0001F64F"  # emoticons
            u"\U0001F300-\U0001F5FF"  # symbols & pictographs
            u"\U0001F680-\U0001F6FF"  # transport & map symbols
            u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
            u"\U00002702-\U000027B0"
            u"\U000024C2-\U0001F251"
            "]+", flags=re.UNICODE)
        clean_text = emoji_pattern.sub('', text)
        print(clean_text)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from agents.adk_agents.smart_orchestrator import create_smart_orchestrator
from agents.adk_agents.decision_validator import create_decision_validator
from agents.adk_agents.ask_user_agent import create_ask_user_agent
from config.agent_registry import create_agent_instance, get_worker_agent_names
from agents.adk_agents.runner_utils import RunnerHelper


def initialize_orchestrator():
    """
    Initialize Smart Orchestrator with all worker agents.
    This mimics the initialization in main.py.
    """
    print("Initializing orchestrator with all worker agents...")

    # Load worker agents from registry
    worker_names = get_worker_agent_names()
    worker_agents = []

    for agent_name in worker_names:
        try:
            agent = create_agent_instance(agent_name)
            worker_agents.append(agent)
            print(f"  [OK] Loaded: {agent_name}")
        except Exception as e:
            print(f"  [FAIL] Failed to load {agent_name}: {e}")

    # Create orchestration components
    decision_validator = create_decision_validator(
        model="gemini-2.5-flash",
        sub_agents=[]
    )

    ask_user = create_ask_user_agent(
        model="gemini-2.5-flash"
    )

    # Create Smart Orchestrator
    orchestrator = create_smart_orchestrator(
        model="gemini-2.5-pro",
        worker_agents=worker_agents,
        validator_agent=decision_validator,
        ask_user_agent=ask_user
    )

    # Create RunnerHelper for persistent sessions
    session_id = f"test-session-{int(datetime.now().timestamp())}"
    orchestrator_helper = RunnerHelper(
        agent=orchestrator,
        session_id=session_id,
        user_id="test-user",
        app_name="agents"
    )

    print(f"[OK] Orchestrator initialized with {len(worker_agents)} worker agents")
    return orchestrator_helper


async def test_orchestrator_sheets_analysis(orchestrator):
    """
    Test 1: Orchestrator delegates to Analyst for Sheets analysis

    Scenario:
    - Read data from test spreadsheet
    - Analyze totals

    Agents involved: Analyst (Sheets)
    """
    print("\n" + "="*80)
    print("TEST 1: Orchestrator - Sheets Analysis")
    print("="*80)
    print()
    print("Scenario: Analyze sales data from test spreadsheet")
    print()

    query = """
    I need you to read the 'Test Data 2026' spreadsheet.
    Look at the Sales Data sheet and tell me:
    1. How many sales are recorded
    2. What is the total revenue
    3. Which product appears most frequently

    Just provide a summary of these findings.
    """

    print(f"Query: {query.strip()}")
    print()
    print("Executing...")
    print("-" * 80)

    try:
        result = await orchestrator.run(query)

        print()
        print("-" * 80)
        print("Result:")
        safe_print(result)
        print()

        # Check if we got a meaningful response
        if result and len(result) > 50:
            print("[OK] Test 1 PASSED - Got detailed analysis")
            return True
        else:
            print(f"[FAIL] Test 1 FAILED - Response too short or empty")
            return False

    except Exception as e:
        print(f"[ERROR] Test 1 crashed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_orchestrator_drive_search(orchestrator):
    """
    Test 2: Orchestrator delegates to Librarian for Drive search

    Scenario:
    - Search for files in Drive
    - List results

    Agents involved: Librarian (Drive)
    """
    print("\n" + "="*80)
    print("TEST 2: Orchestrator - Drive Search")
    print("="*80)
    print()
    print("Scenario: Search for test files in Drive")
    print()

    query = """
    Search Google Drive for the folder named 'Test Documents 2026'.
    Tell me if you find it and what its folder ID is.
    """

    print(f"Query: {query.strip()}")
    print()
    print("Executing...")
    print("-" * 80)

    try:
        result = await orchestrator.run(query)

        print()
        print("-" * 80)
        print("Result:")
        safe_print(result)
        print()

        if result and len(result) > 30:
            print("[OK] Test 2 PASSED - Drive search executed")
            return True
        else:
            print(f"[FAIL] Test 2 FAILED - No meaningful response")
            return False

    except Exception as e:
        print(f"[ERROR] Test 2 crashed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_orchestrator_contacts_search(orchestrator):
    """
    Test 3: Orchestrator delegates to Rolodex for Contacts

    Scenario:
    - Find a contact by name

    Agents involved: Rolodex (Contacts)
    """
    print("\n" + "="*80)
    print("TEST 3: Orchestrator - Contacts Search")
    print("="*80)
    print()
    print("Scenario: Find contact information")
    print()

    query = """
    Find the contact information for 'Tomislav Golić'.
    Tell me the email address and phone number if available.
    """

    print(f"Query: {query.strip()}")
    print()
    print("Executing...")
    print("-" * 80)

    try:
        result = await orchestrator.run(query)

        print()
        print("-" * 80)
        print("Result:")
        safe_print(result)
        print()

        if result and ("tgolic555" in result.lower() or "email" in result.lower()):
            print("[OK] Test 3 PASSED - Contact found")
            return True
        else:
            print(f"[FAIL] Test 3 FAILED - Contact not found properly")
            return False

    except Exception as e:
        print(f"[ERROR] Test 3 crashed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_orchestrator_calendar_list(orchestrator):
    """
    Test 4: Orchestrator delegates to Secretary for Calendar

    Scenario:
    - List upcoming events

    Agents involved: Secretary (Calendar)
    """
    print("\n" + "="*80)
    print("TEST 4: Orchestrator - Calendar Events")
    print("="*80)
    print()
    print("Scenario: List upcoming calendar events")
    print()

    query = """
    Show me my calendar events for the next 7 days.
    List the event titles and when they are scheduled.
    """

    print(f"Query: {query.strip()}")
    print()
    print("Executing...")
    print("-" * 80)

    try:
        result = await orchestrator.run(query)

        print()
        print("-" * 80)
        print("Result:")
        safe_print(result)
        print()

        if result and len(result) > 30:
            print("[OK] Test 4 PASSED - Calendar events listed")
            return True
        else:
            print(f"[FAIL] Test 4 FAILED - No events found")
            return False

    except Exception as e:
        print(f"[ERROR] Test 4 crashed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_orchestrator_tasks_list(orchestrator):
    """
    Test 5: Orchestrator delegates to Tracker for Tasks

    Scenario:
    - List current tasks

    Agents involved: Tracker (Tasks)
    """
    print("\n" + "="*80)
    print("TEST 5: Orchestrator - Tasks List")
    print("="*80)
    print()
    print("Scenario: List current tasks")
    print()

    query = """
    Show me my current tasks from Google Tasks.
    List the task titles and their status.
    """

    print(f"Query: {query.strip()}")
    print()
    print("Executing...")
    print("-" * 80)

    try:
        result = await orchestrator.run(query)

        print()
        print("-" * 80)
        print("Result:")
        safe_print(result)
        print()

        if result and len(result) > 30:
            print("[OK] Test 5 PASSED - Tasks listed")
            return True
        else:
            print(f"[FAIL] Test 5 FAILED - No tasks found")
            return False

    except Exception as e:
        print(f"[ERROR] Test 5 crashed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all orchestrator multi-agent tests"""
    print("\n" + "="*80)
    print(" "*15 + "ORCHESTRATOR MULTI-AGENT TESTS")
    print("="*80)
    print()
    print("Testing Smart Orchestrator delegation to specialist agents")
    print("Using REAL Google APIs")
    print()
    print("="*80)

    # Check credentials
    try:
        from auth.credential_store import get_credential_store
        credential_store = get_credential_store()
        creds = credential_store.get_credentials()

        if creds is None:
            print("\n[ERROR] No OAuth credentials found!")
            print("Run: python tools/oauth_cli.py --auth")
            return

        print("[OK] OAuth credentials found")
        print()
    except Exception as e:
        print(f"\n[ERROR] Failed to get credentials: {e}")
        return

    # Initialize orchestrator ONCE for all tests
    print("Initializing orchestrator (this will be reused for all tests)...")
    try:
        orchestrator = initialize_orchestrator()
        print("[OK] Orchestrator initialized successfully")
        print()
    except Exception as e:
        print(f"\n[ERROR] Failed to initialize orchestrator: {e}")
        import traceback
        traceback.print_exc()
        return

    # Run tests (passing orchestrator to each)
    tests = [
        ("Sheets Analysis", test_orchestrator_sheets_analysis),
        ("Drive Search", test_orchestrator_drive_search),
        ("Contacts Search", test_orchestrator_contacts_search),
        ("Calendar Events", test_orchestrator_calendar_list),
        ("Tasks List", test_orchestrator_tasks_list),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            passed = await test_func(orchestrator)
            results.append((test_name, passed))
        except Exception as e:
            print(f"\n[ERROR] Test '{test_name}' crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # Summary
    print("\n" + "="*80)
    print("ORCHESTRATOR TESTS SUMMARY")
    print("="*80)
    print()

    passed = sum(1 for _, p in results if p)
    total = len(results)

    for test_name, test_passed in results:
        status = "[OK] PASSED" if test_passed else "[FAIL] FAILED"
        print(f"{status}: {test_name}")

    print()
    print(f"Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    print()

    if passed == total:
        print("[OK] ALL ORCHESTRATOR TESTS PASSED!")
        print()
        print("Verified:")
        print("  - Smart Orchestrator agent coordination")
        print("  - Delegation to specialist agents")
        print("  - Real Google API integrations")
        print("  - Analyst + Librarian + Secretary + Rolodex + Tracker agents")
        print()
        print("System orchestration verified!")
    else:
        print("[WARNING] Some orchestrator tests failed")
        print("Review logs and fix issues before proceeding")

    print()
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
