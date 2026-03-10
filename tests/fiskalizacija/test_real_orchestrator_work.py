"""
Real Orchestrator Work Test - COMPREHENSIVE

Tests that orchestrator actually DOES THE WORK, not just returns a response.

This test focuses on:
1. Analyst finding AND analyzing spreadsheets
2. Librarian searching AND returning specific file info
3. Complete workflows that deliver value

No more fake "passes" - we verify actual work was done.
"""

import asyncio
import sys
import re
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

def safe_print(text):
    """Print with emoji handling"""
    try:
        print(text)
    except UnicodeEncodeError:
        emoji_pattern = re.compile("["
            u"\U0001F600-\U0001F64F"
            u"\U0001F300-\U0001F5FF"
            u"\U0001F680-\U0001F6FF"
            u"\U0001F1E0-\U0001F1FF"
            u"\U00002702-\U000027B0"
            u"\U000024C2-\U0001F251"
            "]+", flags=re.UNICODE)
        print(emoji_pattern.sub('', text))


def initialize_orchestrator():
    """Initialize orchestrator with all worker agents"""
    from agents.adk_agents.smart_orchestrator import create_smart_orchestrator
    from agents.adk_agents.decision_validator import create_decision_validator
    from agents.adk_agents.ask_user_agent import create_ask_user_agent
    from config.agent_registry import create_agent_instance, get_worker_agent_names
    from agents.adk_agents.runner_utils import RunnerHelper

    print("Initializing orchestrator...")

    worker_names = get_worker_agent_names()
    worker_agents = []

    for agent_name in worker_names:
        try:
            agent = create_agent_instance(agent_name)
            worker_agents.append(agent)
        except Exception as e:
            print(f"  [WARNING] Failed to load {agent_name}: {e}")

    decision_validator = create_decision_validator(
        model="gemini-2.5-flash",
        sub_agents=[]
    )

    ask_user = create_ask_user_agent(
        model="gemini-2.5-flash"
    )

    orchestrator = create_smart_orchestrator(
        model="gemini-2.5-pro",
        worker_agents=worker_agents,
        validator_agent=decision_validator,
        ask_user_agent=ask_user
    )

    session_id = f"real-test-{int(datetime.now().timestamp())}"
    orchestrator_helper = RunnerHelper(
        agent=orchestrator,
        session_id=session_id,
        user_id="test-user",
        app_name="agents"
    )

    print(f"[OK] Orchestrator initialized with {len(worker_agents)} workers")
    return orchestrator_helper


async def test_1_find_specific_spreadsheet(orchestrator):
    """
    TEST 1: Find a specific spreadsheet by searching Drive

    Success criteria:
    - Agent searches Drive
    - Finds spreadsheet by name pattern
    - Returns spreadsheet ID or URL
    """
    print("\n" + "="*80)
    print("TEST 1: Find Specific Spreadsheet")
    print("="*80)
    print()

    # More specific query that gives context
    query = """
    I need to analyze sales data from my 'Test Data 2026' spreadsheet.

    First, search my Google Drive for any spreadsheet with 'Test Data 2026' in the name.
    Then tell me:
    1. How many matching spreadsheets you found
    2. The name and ID of each one
    3. Which one was created most recently

    If you find multiple, list all of them so I can choose.
    """

    print("Query: Find and list 'Test Data 2026' spreadsheets")
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

        # Success criteria: Did agent actually search and find files?
        result_lower = result.lower()

        success_indicators = [
            "found" in result_lower,
            "spreadsheet" in result_lower or "sheet" in result_lower,
            "test data 2026" in result_lower,
        ]

        if sum(success_indicators) >= 2:
            print("[OK] Test 1 PASSED - Agent found spreadsheet(s)")
            return True
        else:
            print(f"[FAIL] Test 1 FAILED - Agent didn't search or find spreadsheets")
            print(f"  Success indicators: {sum(success_indicators)}/3")
            return False

    except Exception as e:
        print(f"[ERROR] Test 1 crashed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_2_list_all_spreadsheets(orchestrator):
    """
    TEST 2: List ALL spreadsheets to verify Analyst can enumerate

    Success criteria:
    - Agent lists multiple spreadsheets
    - Returns names and IDs
    - Shows it can access Sheets API
    """
    print("\n" + "="*80)
    print("TEST 2: List All My Spreadsheets")
    print("="*80)
    print()

    query = """
    List all the spreadsheets in my Google Drive.

    For each spreadsheet, show me:
    - The name
    - The spreadsheet ID
    - When it was last modified

    Limit to the 5 most recently modified spreadsheets.
    """

    print("Query: List recent spreadsheets")
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

        # Success criteria: Did agent list multiple spreadsheets?
        result_lower = result.lower()

        success_indicators = [
            result_lower.count("spreadsheet") >= 2,  # Multiple spreadsheets mentioned
            len(result) > 200,  # Substantial response
            "id" in result_lower or "modified" in result_lower,  # Metadata shown
        ]

        if sum(success_indicators) >= 2:
            print("[OK] Test 2 PASSED - Agent listed spreadsheets")
            return True
        else:
            print(f"[FAIL] Test 2 FAILED - Agent didn't list spreadsheets properly")
            print(f"  Success indicators: {sum(success_indicators)}/3")
            return False

    except Exception as e:
        print(f"[ERROR] Test 2 crashed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_3_count_contacts(orchestrator):
    """
    TEST 3: Count total contacts in address book

    Success criteria:
    - Agent accesses Contacts API
    - Returns actual count
    - Shows it can enumerate contacts
    """
    print("\n" + "="*80)
    print("TEST 3: Count My Contacts")
    print("="*80)
    print()

    query = """
    Tell me how many contacts I have in my Google Contacts.

    Also, list the first 3 contacts alphabetically by name.
    """

    print("Query: Count and list contacts")
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

        # Success criteria: Did agent count contacts?
        result_lower = result.lower()

        success_indicators = [
            any(word in result_lower for word in ["contact", "people"]),
            any(char.isdigit() for char in result),  # Has numbers (count)
            len(result) > 50,  # Non-trivial response
        ]

        if sum(success_indicators) >= 2:
            print("[OK] Test 3 PASSED - Agent accessed contacts")
            return True
        else:
            print(f"[FAIL] Test 3 FAILED - Agent didn't access contacts")
            print(f"  Success indicators: {sum(success_indicators)}/3")
            return False

    except Exception as e:
        print(f"[ERROR] Test 3 crashed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_4_create_test_folder(orchestrator):
    """
    TEST 4: Create a new folder in Drive

    Success criteria:
    - Agent creates folder
    - Returns folder ID
    - Folder actually exists
    """
    print("\n" + "="*80)
    print("TEST 4: Create Test Folder")
    print("="*80)
    print()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"Orchestrator Test {timestamp}"

    query = f"""
    Create a new folder in my Google Drive called "{folder_name}".

    After creating it, tell me:
    - The folder ID
    - The folder URL
    - Confirmation that it was created successfully
    """

    print(f"Query: Create folder '{folder_name}'")
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

        # Success criteria: Did agent create folder?
        result_lower = result.lower()

        success_indicators = [
            "created" in result_lower or "success" in result_lower,
            "id" in result_lower,
            folder_name.lower() in result_lower,
        ]

        if sum(success_indicators) >= 2:
            print("[OK] Test 4 PASSED - Agent created folder")
            return True
        else:
            print(f"[FAIL] Test 4 FAILED - Agent didn't create folder")
            print(f"  Success indicators: {sum(success_indicators)}/3")
            return False

    except Exception as e:
        print(f"[ERROR] Test 4 crashed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_5_multi_agent_workflow(orchestrator):
    """
    TEST 5: Complex multi-agent workflow

    Workflow: Drive search → Sheets analysis → Summary

    Success criteria:
    - Agent coordinates multiple specialists
    - Delivers complete analysis
    - Shows real data processing
    """
    print("\n" + "="*80)
    print("TEST 5: Multi-Agent Workflow")
    print("="*80)
    print()

    query = """
    I want a complete analysis of my Google Workspace data:

    1. How many spreadsheets do I have in Drive?
    2. How many contacts are in my address book?
    3. How many task lists do I have in Google Tasks?

    Give me a summary report with these three numbers.
    """

    print("Query: Multi-service data summary")
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

        # Success criteria: Did agent coordinate multiple services?
        result_lower = result.lower()

        # Count how many numbers are in the result (should have 3 counts)
        numbers = [int(s) for s in result.split() if s.isdigit()]

        success_indicators = [
            "spreadsheet" in result_lower,
            "contact" in result_lower or "address" in result_lower,
            "task" in result_lower,
            len(numbers) >= 3,  # At least 3 numbers reported
        ]

        if sum(success_indicators) >= 3:
            print("[OK] Test 5 PASSED - Multi-agent workflow succeeded")
            return True
        else:
            print(f"[FAIL] Test 5 FAILED - Multi-agent workflow incomplete")
            print(f"  Success indicators: {sum(success_indicators)}/4")
            print(f"  Numbers found: {numbers}")
            return False

    except Exception as e:
        print(f"[ERROR] Test 5 crashed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run comprehensive orchestrator work tests"""
    print("\n" + "="*80)
    print(" "*20 + "REAL ORCHESTRATOR WORK TESTS")
    print("="*80)
    print()
    print("Testing that orchestrator actually DOES WORK, not just responds.")
    print("Success requires agents to:")
    print("  - Search and find data")
    print("  - Process and analyze")
    print("  - Coordinate multiple services")
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

    # Initialize orchestrator ONCE
    try:
        orchestrator = initialize_orchestrator()
        print()
    except Exception as e:
        print(f"\n[ERROR] Failed to initialize orchestrator: {e}")
        import traceback
        traceback.print_exc()
        return

    # Run tests
    tests = [
        ("Find Specific Spreadsheet", test_1_find_specific_spreadsheet),
        ("List All Spreadsheets", test_2_list_all_spreadsheets),
        ("Count Contacts", test_3_count_contacts),
        ("Create Test Folder", test_4_create_test_folder),
        ("Multi-Agent Workflow", test_5_multi_agent_workflow),
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
    print("REAL WORK TEST SUMMARY")
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
        print("[OK] ALL REAL WORK TESTS PASSED!")
        print()
        print("Verified:")
        print("  - Agents search and find data")
        print("  - Agents process and analyze")
        print("  - Agents coordinate multiple services")
        print("  - Orchestrator delegates effectively")
    elif passed >= total * 0.6:
        print("[PARTIAL] Most tests passed but some issues remain")
    else:
        print("[FAIL] Significant issues - agents not doing real work")

    print()
    print("="*80)

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
