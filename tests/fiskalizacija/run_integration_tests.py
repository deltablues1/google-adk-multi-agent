"""
Integration Test Runner for Google Workspace ADK Multi-Agent System

Tests multi-agent workflows where 2+ agents work together.
Starts with simple 2-agent workflows and progresses to complex 3+ agent scenarios.
"""

import os
import sys
import asyncio
import logging
import time
from pathlib import Path
from datetime import datetime

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


async def run_single_test(system: WorkspaceADKSystem, query: str, test_name: str = "", category: str = ""):
    """
    Run a single integration test query.

    Args:
        system: WorkspaceADKSystem instance
        query: Test query string
        test_name: Optional test name for logging
        category: Test category for context

    Returns:
        tuple: (success: bool, response: str, error: Optional[str], duration: float)
    """
    print("\n" + "="*80)
    if category:
        print(f"CATEGORY: {category}")
    if test_name:
        print(f"TEST: {test_name}")
    print(f"QUERY: {query}")
    print("="*80)

    start_time = time.time()

    try:
        # Process through orchestrator
        logger.info(f"Processing: {query}")

        # Route through master router
        from agents.base_agent import BaseAgent
        router_response = await system.master_router.run_with_fallback(query)

        if "CLASSROOM" in router_response.upper():
            system.active_mode = "CLASSROOM"
            logger.info("Routing to CLASSROOM mode (Socrates)")
            print("\n[SOCRATES] Socrates is thinking...")
            response = await system.socrates.run_with_fallback(query)
            print(sanitize_emojis(f"\n[SOCRATES] Socrates:\n{response}"))
        else:
            system.active_mode = "LEGACY"
            logger.info("Routing to LEGACY mode (Orchestrator)")
            print("\n[PROCESSING] Multi-agent orchestration in progress...")
            response = await system.orchestrator_helper.run(query)
            print(sanitize_emojis(f"\n[OK] Result:\n{response}"))

        duration = time.time() - start_time
        print(f"\n[TIMING] Completed in {duration:.2f}s")

        return (True, response, None, duration)

    except Exception as e:
        duration = time.time() - start_time
        error_msg = str(e)
        logger.error(f"Test failed: {error_msg}")
        print(f"\n[ERROR] ERROR: {error_msg}")
        print(f"\n[TIMING] Failed after {duration:.2f}s")
        return (False, None, error_msg, duration)


async def run_test_category(system: WorkspaceADKSystem, category_name: str, tests: list):
    """
    Run a category of integration tests.

    Args:
        system: WorkspaceADKSystem instance
        category_name: Name of test category
        tests: List of (test_name, query) tuples

    Returns:
        List of test results
    """
    print("\n\n" + "#"*80)
    print(f"# INTEGRATION TEST CATEGORY: {category_name}")
    print("#"*80)

    results = []
    for test_name, query in tests:
        success, response, error, duration = await run_single_test(
            system, query, test_name, category_name
        )
        results.append({
            'name': test_name,
            'query': query,
            'success': success,
            'response': response,
            'error': error,
            'duration': duration,
            'category': category_name
        })

        # Delay between tests to avoid rate limits
        await asyncio.sleep(2)

    # Category summary
    passed = sum(1 for r in results if r['success'])
    failed = len(results) - passed
    avg_duration = sum(r['duration'] for r in results) / len(results) if results else 0

    print("\n" + "="*80)
    print(f"CATEGORY SUMMARY: {category_name}")
    print(f"Total: {len(results)} | Passed: {passed} | Failed: {failed}")
    print(f"Average Duration: {avg_duration:.2f}s")
    print("="*80)

    if failed > 0:
        print("\nFAILED TESTS:")
        for r in results:
            if not r['success']:
                print(f"  [ERROR] {r['name']}")
                print(f"          Error: {r['error']}")

    return results


async def main():
    """Main integration test runner"""
    print("\n" + "="*80)
    print("INTEGRATION TEST RUNNER - MULTI-AGENT WORKFLOWS")
    print("="*80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Initialize system
    print("\nInitializing multi-agent system...")
    system = WorkspaceADKSystem()
    system.initialize_agents()

    print(f"\nSession ID: {system.session_id}")
    print(f"User ID: {system.user_id}")
    print("OAuth: Authenticated")
    print("\n" + "="*80)

    all_results = []

    # ========================================================================
    # PHASE 1: Simple 2-Agent Workflows
    # ========================================================================
    print("\n\n" + "="*80)
    print("= PHASE 1: SIMPLE 2-AGENT WORKFLOWS")
    print("="*80)

    # Category 2.1: Research -> Document
    research_doc_tests = [
        ("Research->Doc-1: AI trends summary",
         "Istraži najnovije trendove u AI i napiši mi sažetak u Google Doc"),

        ("Research->Doc-2: Claude API pricing",
         "Pronađi informacije o Claude API pricing i stvori dokument sa rezultatima"),
    ]
    results_2_1 = await run_test_category(
        system,
        "2.1 Research -> Document (Researcher + Scribe)",
        research_doc_tests
    )
    all_results.extend(results_2_1)

    # Category 2.3: Calendar -> Tasks
    calendar_tasks_tests = [
        ("Calendar->Tasks-1: Tomorrow meetings to tasks",
         "Pronađi sve sastanke za sutra i stvori zadatke za pripremu"),
    ]
    results_2_3 = await run_test_category(
        system,
        "2.3 Calendar -> Tasks (Secretary + Tracker)",
        calendar_tasks_tests
    )
    all_results.extend(results_2_3)

    # Category 2.4: Email -> Tasks
    email_tasks_tests = [
        ("Email->Tasks-1: Extract action items",
         "Izvuci action items iz zadnjih 5 emailova i stvori zadatke"),
    ]
    results_2_4 = await run_test_category(
        system,
        "2.4 Email -> Tasks (Mailer + Tracker)",
        email_tasks_tests
    )
    all_results.extend(results_2_4)

    # ========================================================================
    # PHASE 2: Complex 3+ Agent Workflows
    # ========================================================================
    print("\n\n" + "="*80)
    print("= PHASE 2: COMPLEX 3+ AGENT WORKFLOWS")
    print("="*80)

    # Category 3.1: Research -> Document -> Email
    research_doc_email_tests = [
        ("Research->Doc->Email-1: Python testing best practices",
         "Istraži best practices za Python testing, napiši dokument, i pošalji dev timu"),
    ]
    results_3_1 = await run_test_category(
        system,
        "3.1 Research -> Document -> Email (3 agents)",
        research_doc_email_tests
    )
    all_results.extend(results_3_1)

    # ========================================================================
    # OVERALL SUMMARY
    # ========================================================================
    print("\n\n" + "="*80)
    print("INTEGRATION TEST RUN COMPLETE - COMPREHENSIVE REPORT")
    print("="*80)
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    total = len(all_results)
    passed = sum(1 for r in all_results if r['success'])
    failed = total - passed
    total_duration = sum(r['duration'] for r in all_results)
    avg_duration = total_duration / total if total > 0 else 0

    print(f"\nOverall Results:")
    print(f"  Total Tests: {total}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print(f"  Success Rate: {(passed/total*100) if total > 0 else 0:.1f}%")
    print(f"  Total Duration: {total_duration:.2f}s")
    print(f"  Average Duration: {avg_duration:.2f}s")

    # Category breakdown
    print(f"\nCategory Breakdown:")
    print(f"  2.1 Research -> Document: {sum(1 for r in results_2_1 if r['success'])}/{len(research_doc_tests)}")
    print(f"  2.3 Calendar -> Tasks: {sum(1 for r in results_2_3 if r['success'])}/{len(calendar_tasks_tests)}")
    print(f"  2.4 Email -> Tasks: {sum(1 for r in results_2_4 if r['success'])}/{len(email_tasks_tests)}")
    print(f"  3.1 Research -> Doc -> Email: {sum(1 for r in results_3_1 if r['success'])}/{len(research_doc_email_tests)}")

    # Failed tests summary
    if failed > 0:
        print(f"\n\nFAILED TESTS SUMMARY:")
        for r in all_results:
            if not r['success']:
                print(f"  [ERROR] {r['name']}")
                print(f"          Category: {r['category']}")
                print(f"          Query: {r['query']}")
                print(f"          Error: {r['error']}")
                print(f"          Duration: {r['duration']:.2f}s\n")

    # Save detailed results
    results_file = Path(__file__).parent / "integration_test_results.txt"
    with open(results_file, 'w', encoding='utf-8') as f:
        f.write(f"Integration Test Results\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"="*80 + "\n\n")

        for r in all_results:
            f.write(f"Test: {r['name']}\n")
            f.write(f"Category: {r['category']}\n")
            f.write(f"Query: {r['query']}\n")
            f.write(f"Success: {r['success']}\n")
            f.write(f"Duration: {r['duration']:.2f}s\n")
            if r['error']:
                f.write(f"Error: {r['error']}\n")
            if r['response']:
                f.write(f"Response:\n{r['response']}\n")
            f.write("-"*80 + "\n\n")

    print(f"\n[OK] Detailed results saved to: {results_file}")

    print("\n" + "="*80)
    print("Next Steps:")
    print("  - Review failed tests above")
    print("  - Check integration_test_results.txt for full details")
    print("  - Once 2-3 agent workflows pass, proceed to Fiskalizacija tests")
    print("="*80)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nIntegration test run interrupted")
    except Exception as e:
        logger.error(f"Integration test runner error: {e}")
        raise
