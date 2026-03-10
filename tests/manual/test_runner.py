"""
Automated Test Runner for Multi-Agent System
Tests key workflows with real data and logs results
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
import json
from typing import Dict, List, Any
import traceback

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from agents.adk_agents.smart_orchestrator import create_orchestrator_agent
from google_adk.runners.cli_runner import CliRunner

# Test Configuration
REAL_USER_EMAIL = "tgolic555@gmail.com"
REAL_USER_NAME = "Tomislav Golić"
NEW_CONTACT_NAME = "Davor Golić"
NEW_CONTACT_EMAIL = "davor_golic@hotmail.com"
NEW_CONTACT_PHONE = "0915584072"

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

class TestRunner:
    def __init__(self):
        self.results = []
        self.log_file = project_root / f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self.passed = 0
        self.failed = 0
        self.skipped = 0

    def log(self, message: str, level: str = "INFO"):
        """Log message to both console and file"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] [{level}] {message}"

        # Console output with colors
        if level == "SUCCESS":
            print(f"{Colors.GREEN}✅ {message}{Colors.RESET}")
        elif level == "FAILURE":
            print(f"{Colors.RED}❌ {message}{Colors.RESET}")
        elif level == "SKIP":
            print(f"{Colors.YELLOW}⏭️  {message}{Colors.RESET}")
        elif level == "INFO":
            print(f"{Colors.CYAN}ℹ️  {message}{Colors.RESET}")
        elif level == "TEST":
            print(f"{Colors.BOLD}{Colors.BLUE}🧪 {message}{Colors.RESET}")
        else:
            print(f"   {message}")

        # File output
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_line + '\n')

    async def run_test(self, test_name: str, query: str, expected_agent: str = None, should_fail: bool = False) -> Dict[str, Any]:
        """Run a single test query"""
        self.log(f"Testing: {test_name}", "TEST")
        self.log(f"Query: {query}", "INFO")

        result = {
            'test_name': test_name,
            'query': query,
            'expected_agent': expected_agent,
            'should_fail': should_fail,
            'timestamp': datetime.now().isoformat(),
            'success': False,
            'error': None,
            'response': None,
            'agent_used': None
        }

        try:
            # Create orchestrator
            orchestrator = create_orchestrator_agent()
            runner = CliRunner(orchestrator, verbose=True)

            # Run query
            self.log(f"Executing query...", "INFO")
            response = await runner.run_turn(query)

            result['response'] = str(response)[:500]  # First 500 chars
            result['success'] = True

            # Check if expected agent was used (basic check in response)
            if expected_agent:
                response_lower = str(response).lower()
                agent_found = expected_agent.lower() in response_lower
                result['agent_used'] = expected_agent if agent_found else "Unknown"

                if agent_found:
                    self.log(f"Expected agent '{expected_agent}' was used ✓", "SUCCESS")
                else:
                    self.log(f"Warning: Expected agent '{expected_agent}' not clearly identified", "INFO")

            if should_fail:
                self.log(f"Test FAILED: Expected failure but succeeded", "FAILURE")
                result['success'] = False
                self.failed += 1
            else:
                self.log(f"Test PASSED: {test_name}", "SUCCESS")
                self.passed += 1

        except Exception as e:
            result['error'] = str(e)
            result['traceback'] = traceback.format_exc()

            if should_fail:
                self.log(f"Test PASSED: Expected failure occurred - {str(e)[:100]}", "SUCCESS")
                result['success'] = True
                self.passed += 1
            else:
                self.log(f"Test FAILED: {str(e)[:100]}", "FAILURE")
                self.log(f"Traceback: {traceback.format_exc()}", "INFO")
                self.failed += 1

        self.results.append(result)
        self.log("─" * 80, "INFO")

        # Small delay between tests
        await asyncio.sleep(2)

        return result

    async def run_all_tests(self):
        """Run comprehensive test suite"""
        self.log("=" * 80, "INFO")
        self.log("STARTING AUTOMATED TEST SUITE", "TEST")
        self.log(f"Log file: {self.log_file}", "INFO")
        self.log("=" * 80, "INFO")

        # Calculate dates for testing
        today = datetime.now()
        tomorrow = today + timedelta(days=1)
        next_friday = today + timedelta(days=(4 - today.weekday()) % 7)

        today_str = today.strftime("%Y-%m-%d")
        tomorrow_str = tomorrow.strftime("%Y-%m-%d")
        friday_str = next_friday.strftime("%Y-%m-%d")

        # ============================================================================
        # CATEGORY 1: SINGLE-AGENT TESTS
        # ============================================================================

        self.log("\n" + "=" * 80, "INFO")
        self.log("CATEGORY 1: SINGLE-AGENT TESTS", "TEST")
        self.log("=" * 80 + "\n", "INFO")

        # 1.1 Mailer Tests
        await self.run_test(
            test_name="Mailer: Get last 5 emails",
            query="Pokaži mi zadnjih 5 emailova",
            expected_agent="Mailer"
        )

        await self.run_test(
            test_name="Mailer: Search emails from specific person",
            query=f"Pokaži mi emailove od {REAL_USER_NAME}",
            expected_agent="Mailer"
        )

        await self.run_test(
            test_name="Mailer: Show unread emails",
            query="Pokaži mi nepročitane emailove",
            expected_agent="Mailer"
        )

        # 1.2 Secretary Tests
        await self.run_test(
            test_name="Secretary: Get today's first event",
            query="Koja mi je prva obaveza danas?",
            expected_agent="Secretary"
        )

        await self.run_test(
            test_name="Secretary: List next week events",
            query="Pokaži mi sve sastanke za sljedeći tjedan",
            expected_agent="Secretary"
        )

        # 1.3 Rolodex Tests
        await self.run_test(
            test_name="Rolodex: Find existing contact",
            query=f"Pronađi kontakt {REAL_USER_NAME}",
            expected_agent="Rolodex"
        )

        await self.run_test(
            test_name="Rolodex: Search contact by email",
            query=f"Pronađi kontakt sa emailom {REAL_USER_EMAIL}",
            expected_agent="Rolodex"
        )

        await self.run_test(
            test_name="Rolodex: Add new contact",
            query=f"Dodaj novi kontakt: Ime '{NEW_CONTACT_NAME}', email '{NEW_CONTACT_EMAIL}', telefon '{NEW_CONTACT_PHONE}'",
            expected_agent="Rolodex"
        )

        # 1.4 Tracker Tests
        await self.run_test(
            test_name="Tracker: Add simple task",
            query=f"Dodaj zadatak 'Test zadatak iz automation script' do {friday_str}",
            expected_agent="Tracker"
        )

        await self.run_test(
            test_name="Tracker: List high priority tasks",
            query="Pokaži mi sve moje zadatke sa visokim prioritetom",
            expected_agent="Tracker"
        )

        await self.run_test(
            test_name="Tracker: Show overdue tasks",
            query="Koji mi zadaci kasne (overdue)?",
            expected_agent="Tracker"
        )

        # 1.5 Librarian Tests
        await self.run_test(
            test_name="Librarian: Find PDF documents",
            query="Pronađi sve PDF dokumente u mom Drive-u",
            expected_agent="Librarian"
        )

        await self.run_test(
            test_name="Librarian: List recent files",
            query="Pokaži mi datoteke modificirane u zadnjih 7 dana",
            expected_agent="Librarian"
        )

        # 1.6 Analyst Tests
        await self.run_test(
            test_name="Analyst: Basic sheet query",
            query="Koliko redova ima sheet 'Test Data'?",
            expected_agent="Analyst"
        )

        # 1.7 Researcher Tests
        await self.run_test(
            test_name="Researcher: Web search",
            query="Istraži najnovije AI trendove u 2026",
            expected_agent="Researcher"
        )

        # ============================================================================
        # CATEGORY 2: MULTI-AGENT WORKFLOWS (2 agents)
        # ============================================================================

        self.log("\n" + "=" * 80, "INFO")
        self.log("CATEGORY 2: MULTI-AGENT WORKFLOWS (2 agents)", "TEST")
        self.log("=" * 80 + "\n", "INFO")

        await self.run_test(
            test_name="Research → Email",
            query=f"Istraži cijene Claude API pricing i pošalji kratki sažetak rezultata na {REAL_USER_EMAIL}",
            expected_agent="Orchestrator"
        )

        await self.run_test(
            test_name="Contact → Email",
            query=f"Pronađi kontakt {REAL_USER_NAME} i pošalji mu email sa porukom 'Test email iz automation script'",
            expected_agent="Orchestrator"
        )

        await self.run_test(
            test_name="Calendar → Tasks",
            query=f"Pronađi sve sastanke za sutra ({tomorrow_str}) i stvori zadatke za pripremu",
            expected_agent="Orchestrator"
        )

        # ============================================================================
        # CATEGORY 3: COMPLEX MULTI-AGENT WORKFLOWS (3+ agents)
        # ============================================================================

        self.log("\n" + "=" * 80, "INFO")
        self.log("CATEGORY 3: COMPLEX MULTI-AGENT WORKFLOWS (3+ agents)", "TEST")
        self.log("=" * 80 + "\n", "INFO")

        await self.run_test(
            test_name="Research → Document → Email",
            query=f"Istraži best practices za Python testing, napiši kratak dokument sa sažetkom, i pošalji na {REAL_USER_EMAIL}",
            expected_agent="Orchestrator"
        )

        # ============================================================================
        # CATEGORY 4: EDGE CASES & ERROR HANDLING
        # ============================================================================

        self.log("\n" + "=" * 80, "INFO")
        self.log("CATEGORY 4: EDGE CASES & ERROR HANDLING", "TEST")
        self.log("=" * 80 + "\n", "INFO")

        await self.run_test(
            test_name="Invalid Email Format (Should detect error)",
            query="Pošalji email na 'invalid_email_bez_at_znaka' sa porukom 'test'",
            expected_agent="Mailer",
            should_fail=False  # Agent should handle gracefully with error message
        )

        await self.run_test(
            test_name="Duplicate Contact Detection",
            query=f"Dodaj kontakt '{NEW_CONTACT_NAME}' sa emailom '{NEW_CONTACT_EMAIL}' (već postoji!)",
            expected_agent="Rolodex",
            should_fail=False  # Should detect duplicate and warn
        )

        await self.run_test(
            test_name="Missing Information (Agent should ask)",
            query="Pošalji email Marku",  # Missing: email content, subject
            expected_agent="Mailer",
            should_fail=False  # Should ask for missing info
        )

        # ============================================================================
        # CATEGORY 5: CROATIAN LANGUAGE SUPPORT
        # ============================================================================

        self.log("\n" + "=" * 80, "INFO")
        self.log("CATEGORY 5: CROATIAN LANGUAGE SUPPORT", "TEST")
        self.log("=" * 80 + "\n", "INFO")

        await self.run_test(
            test_name="Croatian Date Format Handling",
            query=f"Stvori sastanak sutra u 14:00 sa naslovom 'Test sastanak {tomorrow.strftime('%d.%m.%Y.')}'",
            expected_agent="Secretary"
        )

        await self.run_test(
            test_name="Croatian Character Preservation",
            query=f"Dodaj zadatak 'Završiti godišnji izvještaj' do {friday_str}",
            expected_agent="Tracker"
        )

        await self.run_test(
            test_name="Croatian Email Composition",
            query=f"Pošalji formalni email na {REAL_USER_EMAIL} sa čestitkama za uspješan projekt",
            expected_agent="Mailer"
        )

        # ============================================================================
        # CATEGORY 6: CONDITIONAL LOGIC
        # ============================================================================

        self.log("\n" + "=" * 80, "INFO")
        self.log("CATEGORY 6: CONDITIONAL LOGIC", "TEST")
        self.log("=" * 80 + "\n", "INFO")

        await self.run_test(
            test_name="IF-THEN Logic",
            query=f"AKO je danas {today.strftime('%A')}, ONDA pošalji mi email sa porukom 'Točno je {today.strftime('%A')}!'",
            expected_agent="Orchestrator"
        )

        # ============================================================================
        # TEST SUMMARY
        # ============================================================================

        self.print_summary()

    def print_summary(self):
        """Print test execution summary"""
        total = self.passed + self.failed + self.skipped

        self.log("\n" + "=" * 80, "INFO")
        self.log("TEST EXECUTION SUMMARY", "TEST")
        self.log("=" * 80, "INFO")

        self.log(f"Total Tests: {total}", "INFO")
        self.log(f"Passed: {self.passed} ({self.passed/total*100:.1f}%)" if total > 0 else "Passed: 0", "SUCCESS")
        self.log(f"Failed: {self.failed} ({self.failed/total*100:.1f}%)" if total > 0 else "Failed: 0", "FAILURE")
        self.log(f"Skipped: {self.skipped}", "SKIP")

        self.log("=" * 80, "INFO")
        self.log(f"Detailed results saved to: {self.log_file}", "INFO")
        self.log("=" * 80, "INFO")

        # Save JSON summary
        summary_file = self.log_file.with_suffix('.json')
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump({
                'summary': {
                    'total': total,
                    'passed': self.passed,
                    'failed': self.failed,
                    'skipped': self.skipped,
                    'success_rate': f"{self.passed/total*100:.1f}%" if total > 0 else "0%"
                },
                'results': self.results
            }, f, indent=2, ensure_ascii=False)

        self.log(f"JSON summary saved to: {summary_file}", "INFO")

async def main():
    """Main entry point"""
    print(f"""
{Colors.BOLD}{Colors.CYAN}
╔═══════════════════════════════════════════════════════════════╗
║         AUTOMATED MULTI-AGENT SYSTEM TEST SUITE              ║
║                                                               ║
║  Testing with real data:                                      ║
║  - User: {REAL_USER_NAME:<50} ║
║  - Email: {REAL_USER_EMAIL:<49} ║
║  - New Contact: {NEW_CONTACT_NAME:<45} ║
╚═══════════════════════════════════════════════════════════════╝
{Colors.RESET}
""")

    runner = TestRunner()

    try:
        await runner.run_all_tests()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}⚠️  Test execution interrupted by user{Colors.RESET}")
        runner.print_summary()
    except Exception as e:
        print(f"\n{Colors.RED}❌ Fatal error: {e}{Colors.RESET}")
        traceback.print_exc()
        runner.print_summary()

if __name__ == "__main__":
    asyncio.run(main())
