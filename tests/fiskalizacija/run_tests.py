"""
Automated Test Runner for Google Workspace ADK Multi-Agent System

Runs tests from docs/testing/test_queries.md without interactive CLI.
Directly calls WorkspaceADKSystem.process_request() for automation.
"""

import os
import sys
import asyncio
import logging
import time
import re
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Import system
sys.path.insert(0, str(Path(__file__).parent))
from main import WorkspaceADKSystem, sanitize_emojis


async def run_single_test(system: WorkspaceADKSystem, query: str, test_name: str = ""):
    """
    Run a single test query against the system.

    Args:
        system: WorkspaceADKSystem instance
        query: Test query string
        test_name: Optional test name for logging

    Returns:
        tuple: (success: bool, response: str, error: Optional[str])
    """
    print("\n" + "="*80)
    if test_name:
        print(f"TEST: {test_name}")
    print(f"QUERY: {query}")
    print("="*80)

    try:
        # Process through master router
        logger.info(f"Processing: {query}")

        # Determine routing (CLASSROOM vs LEGACY)
        from agents.base_agent import BaseAgent
        router_response = await system.master_router.run_with_fallback(query)

        if "CLASSROOM" in router_response.upper():
            system.active_mode = "CLASSROOM"
            logger.info("Routing to CLASSROOM mode (Socrates)")

            # Run Socrates
            print("\n[SOCRATES] Socrates is thinking...")
            response = await system.socrates.run_with_fallback(query)
            print(sanitize_emojis(f"\n[SOCRATES] Socrates:\n{response}"))

        else:
            system.active_mode = "LEGACY"
            logger.info("Routing to LEGACY mode (Orchestrator)")

            # Run through orchestrator
            print("\n[PROCESSING] Processing...")
            response = await system.orchestrator_helper.run(query)
            print(sanitize_emojis(f"\n[OK] Result:\n{response}"))

        return (True, response, None)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Test failed: {error_msg}")
        print(f"\n[ERROR] ERROR: {error_msg}")
        return (False, None, error_msg)


async def run_test_category(system: WorkspaceADKSystem, category_name: str, tests: list):
    """
    Run a category of tests.

    Args:
        system: WorkspaceADKSystem instance
        category_name: Name of test category
        tests: List of (test_name, query) tuples
    """
    print("\n" + "#"*80)
    print(f"# CATEGORY: {category_name}")
    print("#"*80)

    results = []
    for test_name, query in tests:
        success, response, error = await run_single_test(system, query, test_name)
        results.append({
            'name': test_name,
            'query': query,
            'success': success,
            'response': response,
            'error': error
        })

        # Small delay between tests
        await asyncio.sleep(1)

    # Summary
    passed = sum(1 for r in results if r['success'])
    failed = len(results) - passed

    print("\n" + "="*80)
    print(f"CATEGORY SUMMARY: {category_name}")
    print(f"Total: {len(results)} | Passed: {passed} | Failed: {failed}")
    print("="*80)

    if failed > 0:
        print("\nFAILED TESTS:")
        for r in results:
            if not r['success']:
                print(f"  [ERROR] {r['name']}: {r['error']}")

    return results


async def main():
    """Main test runner"""
    print("\n" + "="*80)
    print("AUTOMATED TEST RUNNER")
    print("="*80)

    # Initialize system
    print("\nInitializing system...")
    system = WorkspaceADKSystem()
    system.initialize_agents()

    print(f"\nSession ID: {system.session_id}")
    print(f"User ID: {system.user_id}")
    print("Auth config loaded")

    # === TEST CATEGORIES ===
    print("\n\nStarting comprehensive tests...")

    all_results = []

    # CATEGORY 1.1: MAILER (Single-Agent Basics)
    mailer_tests = [
        ("Mailer-1: Last 5 emails", "Pokaži mi zadnjih 5 emailova"),
        ("Mailer-2: Unread from specific sender", "Pokaži mi nepročitane emailove od Tomislav"),
    ]
    mailer_results = await run_test_category(system, "1.1 Mailer (Email Operations)", mailer_tests)
    all_results.extend(mailer_results)

    # CATEGORY 1.2: SECRETARY (Calendar/Meetings)
    secretary_tests = [
        ("Secretary-1: First task today", "Koja mi je prva obaveza danas?"),
        ("Secretary-2: Show all meetings next week", "Pokaži mi sve sastanke za sljedeći tjedan"),
    ]
    secretary_results = await run_test_category(system, "1.2 Secretary (Calendar/Meetings)", secretary_tests)
    all_results.extend(secretary_results)

    # CATEGORY 1.4: TRACKER (Task Management)
    tracker_tests = [
        ("Tracker-1: Show all tasks", "Pokaži mi sve moje zadatke"),
        ("Tracker-2: High priority tasks", "Pokaži mi zadatke sa visokim prioritetom"),
    ]
    tracker_results = await run_test_category(system, "1.4 Tracker (Task Management)", tracker_tests)
    all_results.extend(tracker_results)

    # CATEGORY 1.7: SCRAPER (FIXED - Priority Test!)
    scraper_tests = [
        ("Scraper-1: Extract pricing table", "Izvuci tablicu cijena sa stranice https://cprz.hr/cjenik-usluga"),
    ]
    scraper_results = await run_test_category(system, "1.7 Scraper (Web Extraction) [FIXED]", scraper_tests)
    all_results.extend(scraper_results)

    # CATEGORY 2.1: RESEARCH → DOCUMENT (Scribe FIXED)
    scribe_tests = [
        ("Scribe-1: Research and create doc", "Istraži najnovije trendove u AI i napiši mi sažetak u Google Doc"),
    ]
    scribe_results = await run_test_category(system, "2.1 Research -> Document (Scribe FIXED)", scribe_tests)
    all_results.extend(scribe_results)

    # OVERALL SUMMARY
    print("\n\n" + "="*80)
    print("TEST RUN COMPLETE - COMPREHENSIVE REPORT")
    print("="*80)

    total = len(all_results)
    passed = sum(1 for r in all_results if r['success'])
    failed = total - passed

    print(f"\nOverall Results:")
    print(f"  Total Tests: {total}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print(f"  Success Rate: {(passed/total*100) if total > 0 else 0:.1f}%")

    # Category breakdown
    print(f"\nCategory Breakdown:")
    print(f"  Mailer: {sum(1 for r in mailer_results if r['success'])}/{len(mailer_tests)}")
    print(f"  Secretary: {sum(1 for r in secretary_results if r['success'])}/{len(secretary_tests)}")
    print(f"  Tracker: {sum(1 for r in tracker_results if r['success'])}/{len(tracker_tests)}")
    print(f"  Scraper (FIXED): {sum(1 for r in scraper_results if r['success'])}/{len(scraper_tests)}")
    print(f"  Scribe (FIXED): {sum(1 for r in scribe_results if r['success'])}/{len(scribe_tests)}")

    # Failed tests summary
    if failed > 0:
        print(f"\n\nFAILED TESTS SUMMARY:")
        for r in all_results:
            if not r['success']:
                print(f"  [ERROR] {r['name']}")
                print(f"          Query: {r['query']}")
                print(f"          Error: {r['error']}\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nTest run interrupted")
    except Exception as e:
        logger.error(f"Test runner error: {e}")
        raise
