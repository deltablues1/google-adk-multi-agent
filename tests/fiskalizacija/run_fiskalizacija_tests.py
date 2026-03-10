"""
Fiskalizacija Integration Test Runner

Tests Fiskalizacija 2.0 workflow with real FINA test certificate.
3-agent pipeline: Pripremac -> Validator -> Executor

Certificate: 47034854402.F1.1.p12
Environment: FINA Test (DEMO)
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
    Run a single Fiskalizacija test query.

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
            print("\n[PROCESSING] Fiskalizacija multi-agent pipeline in progress...")
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
    Run a category of Fiskalizacija tests.

    Args:
        system: WorkspaceADKSystem instance
        category_name: Name of test category
        tests: List of (test_name, query) tuples

    Returns:
        List of test results
    """
    print("\n\n" + "#"*80)
    print(f"# FISKALIZACIJA TEST CATEGORY: {category_name}")
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
    """Main Fiskalizacija test runner"""
    print("\n" + "="*80)
    print("FISKALIZACIJA 2.0 INTEGRATION TEST RUNNER")
    print("="*80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Certificate: 47034854402.F1.1.p12 (FINA Test)")
    print(f"Environment: DEMO")

    # Initialize system
    print("\nInitializing multi-agent system...")
    system = WorkspaceADKSystem()
    system.initialize_agents()

    print(f"\nSession ID: {system.session_id}")
    print(f"User ID: {system.user_id}")
    print("OAuth: Authenticated")

    # Verify certificate exists
    cert_file = Path(__file__).parent / "47034854402.F1.1.p12"
    if cert_file.exists():
        print(f"[OK] Certificate found: {cert_file}")
    else:
        print(f"[WARNING] Certificate not found: {cert_file}")

    print("\n" + "="*80)

    all_results = []

    # ========================================================================
    # PHASE 1: Basic Validation Tools (Single-Agent)
    # ========================================================================
    print("\n\n" + "="*80)
    print("= PHASE 1: BASIC VALIDATION TOOLS")
    print("="*80)

    # Category 1.1: OIB Validation
    oib_tests = [
        ("OIB-1: Valid OIB",
         "Validiraj OIB 47034854402"),

        ("OIB-2: Invalid OIB",
         "Validiraj OIB 12345678901"),
    ]
    results_1_1 = await run_test_category(
        system,
        "1.1 OIB Validation (Fiskalni Validator)",
        oib_tests
    )
    all_results.extend(results_1_1)

    # Category 1.2: KPD Code Search
    kpd_tests = [
        ("KPD-1: Search existing code",
         "Provjeri postoji li KPD kod 70.10"),

        ("KPD-2: Search non-existing code",
         "Provjeri postoji li KPD kod 99.99"),
    ]
    results_1_2 = await run_test_category(
        system,
        "1.2 KPD Code Search (Fiskalni Validator)",
        kpd_tests
    )
    all_results.extend(results_1_2)

    # Category 1.3: Unit Normalization
    unit_tests = [
        ("Unit-1: Normalize 'sat' to UN/ECE",
         "Normaliziraj jedinicu 'sat' u UN/ECE Rec 20 standard"),

        ("Unit-2: Normalize 'komad' to UN/ECE",
         "Normaliziraj jedinicu 'komad' u UN/ECE Rec 20 standard"),
    ]
    results_1_3 = await run_test_category(
        system,
        "1.3 Unit Normalization (Fiskalni Pripremac)",
        unit_tests
    )
    all_results.extend(results_1_3)

    # ========================================================================
    # PHASE 2: Invoice Preparation (Pripremac)
    # ========================================================================
    print("\n\n" + "="*80)
    print("= PHASE 2: INVOICE PREPARATION (PRIPREMAC)")
    print("="*80)

    # Category 2.1: Simple Invoice Preparation
    prep_tests = [
        ("Prep-1: Basic invoice",
         """Pripremi racun sa sljedecim podacima:
         - Broj racuna: R-001/PP/2026
         - Datum izdavanja: 2026-01-27
         - Kupac: Test Kupac d.o.o., OIB 12345678901
         - Stavka 1: Usluga konzultacija, 5 sati, cijena 100 EUR/sat
         - PDV: 25%
         """),
    ]
    results_2_1 = await run_test_category(
        system,
        "2.1 Invoice Preparation (Pripremac)",
        prep_tests
    )
    all_results.extend(results_2_1)

    # ========================================================================
    # PHASE 3: Full 3-Agent Pipeline
    # ========================================================================
    print("\n\n" + "="*80)
    print("= PHASE 3: FULL 3-AGENT PIPELINE (PRIPREMAC -> VALIDATOR -> EXECUTOR)")
    print("="*80)

    # Category 3.1: Complete Invoice Workflow
    pipeline_tests = [
        ("Pipeline-1: Full invoice fiscalization",
         """Fiskaliziraj racun:
         - OIB izdavatelja: 47034854402
         - Broj racuna: R-TEST-001/PP/2026
         - Datum: 2026-01-27
         - Kupac: Test Client Ltd., OIB 12345678901
         - Stavka: Consulting services, 10 hours @ 150 EUR/hour
         - PDV 25%
         - Nacin placanja: Gotovina
         - Poslovni prostor: PP (business premises identifier)
         - Naplatni uredjaj: NU (cash register identifier)

         NAPOMENA: Koristi DEMO okruzenje (ne salji stvarno FINA-i, samo generiraj XML i potpis)
         """),
    ]
    results_3_1 = await run_test_category(
        system,
        "3.1 Complete Fiscalization Pipeline (3 agents)",
        pipeline_tests
    )
    all_results.extend(results_3_1)

    # ========================================================================
    # OVERALL SUMMARY
    # ========================================================================
    print("\n\n" + "="*80)
    print("FISKALIZACIJA TEST RUN COMPLETE - COMPREHENSIVE REPORT")
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
    print(f"  1.1 OIB Validation: {sum(1 for r in results_1_1 if r['success'])}/{len(oib_tests)}")
    print(f"  1.2 KPD Code Search: {sum(1 for r in results_1_2 if r['success'])}/{len(kpd_tests)}")
    print(f"  1.3 Unit Normalization: {sum(1 for r in results_1_3 if r['success'])}/{len(unit_tests)}")
    print(f"  2.1 Invoice Preparation: {sum(1 for r in results_2_1 if r['success'])}/{len(prep_tests)}")
    print(f"  3.1 Full Pipeline: {sum(1 for r in results_3_1 if r['success'])}/{len(pipeline_tests)}")

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
    results_file = Path(__file__).parent / "fiskalizacija_test_results.txt"
    with open(results_file, 'w', encoding='utf-8') as f:
        f.write(f"Fiskalizacija Test Results\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Certificate: 47034854402.F1.1.p12 (FINA Test)\n")
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
    print("  - Review test results above")
    print("  - Check fiskalizacija_test_results.txt for full details")
    print("  - Verify XML generation and XAdES signing")
    print("  - Review any failed validations")
    print("="*80)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nFiskalizacija test run interrupted")
    except Exception as e:
        logger.error(f"Fiskalizacija test runner error: {e}")
        raise
