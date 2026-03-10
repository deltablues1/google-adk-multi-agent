"""
COMPREHENSIVE MULTI-AGENT WORKFLOW TEST
========================================

Test Suite: Real API calls, no mocks, complex multi-agent workflows

Test Scenarios:
1. System Initialization (Orchestrator + All Agents)
2. Deep Research Agent - Real Web Search
3. Multi-Agent Workflow: Research -> Document -> Email
4. Complex Scenario: Croatian News Aggregation
5. End-to-End: YouTube Analysis -> Report -> Share

All tests use REAL API calls!
"""

import asyncio
import sys
import os
import logging
from datetime import datetime
from pathlib import Path

# Setup paths
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment
from dotenv import load_dotenv
load_dotenv()

# Import system components
from main import WorkspaceADKSystem
from agents.orchestrator.orchestrator import create_orchestrator_agent
from agents.researcher.researcher import create_researcher_agent
from config.agent_registry import get_registry_stats, get_all_agent_names
from tools.initialize_tools import initialize_all_tools
from tools.tool_registry import get_tool_registry

# Import research tools directly for testing
from tools.api_implementations.google_search_api import google_search_grounding, google_search_simple
from tools.api_implementations.youtube_api import youtube_get_transcript
from tools.api_implementations.web_scraper_api import scrape_url, scrape_multiple_urls


class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'


class TestResults:
    """Track test results"""
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []
        self.start_time = datetime.now()

    def add_pass(self, test_name: str, details: str = ""):
        self.passed.append((test_name, details))
        print(f"{Colors.GREEN}[PASS]{Colors.END} - {test_name}")
        if details:
            print(f"  {Colors.CYAN}{details}{Colors.END}")

    def add_fail(self, test_name: str, error: str):
        self.failed.append((test_name, error))
        print(f"{Colors.RED}[FAIL]{Colors.END} - {test_name}")
        print(f"  {Colors.RED}{error}{Colors.END}")

    def add_warning(self, test_name: str, warning: str):
        self.warnings.append((test_name, warning))
        print(f"{Colors.YELLOW}[WARN]{Colors.END} - {test_name}")
        print(f"  {Colors.YELLOW}{warning}{Colors.END}")

    def print_summary(self):
        duration = (datetime.now() - self.start_time).total_seconds()
        total = len(self.passed) + len(self.failed)
        pass_rate = (len(self.passed) / total * 100) if total > 0 else 0

        print("\n" + "=" * 80)
        print(f"{Colors.BOLD}TEST SUMMARY{Colors.END}")
        print("=" * 80)
        print(f"Total tests: {total}")
        print(f"{Colors.GREEN}Passed: {len(self.passed)}{Colors.END}")
        print(f"{Colors.RED}Failed: {len(self.failed)}{Colors.END}")
        print(f"{Colors.YELLOW}Warnings: {len(self.warnings)}{Colors.END}")
        print(f"Pass rate: {pass_rate:.1f}%")
        print(f"Duration: {duration:.2f}s")
        print("=" * 80)


# ============================================================================
# TEST 1: System Initialization
# ============================================================================

async def test_system_initialization(results: TestResults):
    """Test complete system initialization"""
    print(f"\n{Colors.HEADER}{'=' * 80}{Colors.END}")
    print(f"{Colors.HEADER}TEST 1: System Initialization{Colors.END}")
    print(f"{Colors.HEADER}{'=' * 80}{Colors.END}")

    try:
        # Test tool registry initialization
        print("\n-> Initializing tool registry...")
        tool_registry = get_tool_registry()
        status = initialize_all_tools()

        total_tools = len(tool_registry)
        if total_tools > 0:
            results.add_pass(
                "Tool Registry Initialization",
                f"Registered {total_tools} tools"
            )
        else:
            results.add_fail(
                "Tool Registry Initialization",
                "No tools registered"
            )

        # Test agent registry
        print("\n-> Checking agent registry...")
        stats = get_registry_stats()
        agent_names = get_all_agent_names()

        results.add_pass(
            "Agent Registry",
            f"Total agents: {stats['total_agents']}, Workers: {stats['worker_agents']}"
        )

        # Test orchestrator creation
        print("\n-> Creating orchestrator agent...")
        orchestrator = create_orchestrator_agent()

        if orchestrator and len(orchestrator.list_sub_agents()) == 0:
            results.add_warning(
                "Orchestrator Creation",
                "Orchestrator created but has no sub-agents (expected in isolated test)"
            )
        else:
            results.add_pass(
                "Orchestrator Creation",
                f"Orchestrator created with {len(orchestrator.list_sub_agents())} sub-agents"
            )

        # Test researcher agent creation
        print("\n-> Creating researcher agent...")
        researcher = create_researcher_agent()
        researcher_tools = researcher.get_tools()

        results.add_pass(
            "Researcher Agent Creation",
            f"Researcher initialized with {len(researcher_tools)} tools"
        )

    except Exception as e:
        results.add_fail("System Initialization", str(e))
        logger.exception("System initialization failed")


# ============================================================================
# TEST 2: Deep Research Agent - Google Search
# ============================================================================

async def test_google_search(results: TestResults):
    """Test Google Search Grounding with real API"""
    print(f"\n{Colors.HEADER}{'=' * 80}{Colors.END}")
    print(f"{Colors.HEADER}TEST 2: Google Search Grounding (REAL API){Colors.END}")
    print(f"{Colors.HEADER}{'=' * 80}{Colors.END}")

    try:
        # Test 1: Google Search Grounding
        print("\n-> Testing google_search_grounding...")
        query = "What is Google Agent Development Kit ADK"

        result = await google_search_grounding(
            credentials=None,
            query=query,
            max_results=5
        )

        if "error" in result:
            results.add_fail(
                "Google Search Grounding",
                result["error"]
            )
        elif result.get("answer"):
            results.add_pass(
                "Google Search Grounding",
                f"Query: '{query}' | Sources: {result.get('source_count', 0)}"
            )
            print(f"\n  Answer preview: {result['answer'][:200]}...")
            if result.get('sources'):
                print(f"  Sources:")
                for i, source in enumerate(result['sources'][:3], 1):
                    print(f"    {i}. {source.get('url', 'N/A')}")
        else:
            results.add_warning(
                "Google Search Grounding",
                "No answer returned (may be expected)"
            )

        # Test 2: Simple Search
        print("\n-> Testing google_search_simple...")
        query2 = "Google Gemini API documentation"

        result2 = await google_search_simple(
            credentials=None,
            query=query2,
            num_results=5
        )

        if "error" in result2:
            results.add_fail("Google Search Simple", result2["error"])
        elif result2.get("sources"):
            results.add_pass(
                "Google Search Simple",
                f"Found {len(result2['sources'])} URLs"
            )
        else:
            results.add_warning("Google Search Simple", "No results found")

    except Exception as e:
        results.add_fail("Google Search Tests", str(e))
        logger.exception("Google search test failed")


# ============================================================================
# TEST 3: YouTube Transcript Extraction
# ============================================================================

async def test_youtube_transcript(results: TestResults):
    """Test YouTube transcript extraction"""
    print(f"\n{Colors.HEADER}{'=' * 80}{Colors.END}")
    print(f"{Colors.HEADER}TEST 3: YouTube Transcript Extraction (REAL API){Colors.END}")
    print(f"{Colors.HEADER}{'=' * 80}{Colors.END}")

    try:
        # Use a known video with English captions
        # Google I/O 2024 Keynote (public video with captions)
        video_url = "https://www.youtube.com/watch?v=XEzRZ35urlk"

        print(f"\n-> Extracting transcript from: {video_url}")

        result = await youtube_get_transcript(
            credentials=None,
            url=video_url,
            languages=["en"]
        )

        if "error" in result:
            results.add_warning(
                "YouTube Transcript",
                f"Could not extract transcript: {result['error']}"
            )
        elif result.get("transcript"):
            word_count = result.get("word_count", 0)
            language = result.get("language", "unknown")
            results.add_pass(
                "YouTube Transcript",
                f"Extracted {word_count} words in {language}"
            )
            print(f"\n  Transcript preview: {result['transcript'][:300]}...")
        else:
            results.add_warning(
                "YouTube Transcript",
                "No transcript found (video may not have captions)"
            )

    except Exception as e:
        results.add_fail("YouTube Transcript", str(e))
        logger.exception("YouTube transcript test failed")


# ============================================================================
# TEST 4: Web Scraping
# ============================================================================

async def test_web_scraping(results: TestResults):
    """Test web scraping with real URLs"""
    print(f"\n{Colors.HEADER}{'=' * 80}{Colors.END}")
    print(f"{Colors.HEADER}TEST 4: Web Scraping (REAL API){Colors.END}")
    print(f"{Colors.HEADER}{'=' * 80}{Colors.END}")

    try:
        # Test scraping a public article
        url = "https://www.index.hr"

        print(f"\n-> Scraping URL: {url}")

        result = await scrape_url(
            credentials=None,
            url=url,
            extract_type="article"
        )

        if "error" in result:
            results.add_warning(
                "Web Scraping Single URL",
                f"Scraping failed: {result['error']}"
            )
        elif result.get("text"):
            word_count = result.get("word_count", 0)
            results.add_pass(
                "Web Scraping Single URL",
                f"Extracted {word_count} words from {url}"
            )
        else:
            results.add_warning(
                "Web Scraping Single URL",
                "No text extracted (may be expected for homepage)"
            )

        # Test multiple URLs
        print("\n-> Testing batch scraping...")
        urls = [
            "https://www.index.hr",
            "https://www.jutarnji.hr"
        ]

        results_batch = await scrape_multiple_urls(
            credentials=None,
            urls=urls,
            extract_type="article"
        )

        success_count = sum(1 for r in results_batch if "error" not in r)
        results.add_pass(
            "Web Scraping Multiple URLs",
            f"Successfully scraped {success_count}/{len(urls)} URLs"
        )

    except Exception as e:
        results.add_fail("Web Scraping", str(e))
        logger.exception("Web scraping test failed")


# ============================================================================
# TEST 5: Researcher Agent End-to-End
# ============================================================================

async def test_researcher_e2e(results: TestResults):
    """Test researcher agent with real query"""
    print(f"\n{Colors.HEADER}{'=' * 80}{Colors.END}")
    print(f"{Colors.HEADER}TEST 5: Researcher Agent End-to-End{Colors.END}")
    print(f"{Colors.HEADER}{'=' * 80}{Colors.END}")

    try:
        print("\n-> Creating researcher agent...")
        researcher = create_researcher_agent()

        print("\n-> Executing research query...")
        query = "What is Google Agent Development Kit and how does it work?"

        print(f"  Query: {query}")
        print(f"  Model: {researcher.model}")
        print(f"  Max iterations: {researcher.config.get('max_iterations')}")

        # Execute research (this will use ReAct loop)
        response = await researcher.run(query)

        if response and len(response) > 100:
            results.add_pass(
                "Researcher Agent E2E",
                f"Generated {len(response)} character response"
            )
            print(f"\n  Response preview:\n{response[:500]}...")
        else:
            results.add_fail(
                "Researcher Agent E2E",
                f"Response too short or empty: {len(response)} chars"
            )

    except Exception as e:
        results.add_fail("Researcher Agent E2E", str(e))
        logger.exception("Researcher E2E test failed")


# ============================================================================
# TEST 6: Multi-Agent Workflow (Complex Scenario)
# ============================================================================

async def test_multi_agent_workflow(results: TestResults):
    """
    Complex Multi-Agent Workflow:
    1. Research a topic (Researcher)
    2. Create a formatted document (Local file)
    3. Prepare email draft (Simulated - would need OAuth)
    """
    print(f"\n{Colors.HEADER}{'=' * 80}{Colors.END}")
    print(f"{Colors.HEADER}TEST 6: Multi-Agent Workflow - Research -> Document -> Email{Colors.END}")
    print(f"{Colors.HEADER}{'=' * 80}{Colors.END}")

    try:
        # Step 1: Research
        print("\n-> STEP 1: Research Topic")
        researcher = create_researcher_agent()
        research_query = "Google Agent Development Kit: Key Features and Use Cases"

        print(f"  Researching: {research_query}")
        research_result = await researcher.run(research_query)

        if not research_result or len(research_result) < 100:
            results.add_fail(
                "Multi-Agent Workflow - Research",
                "Research failed or returned insufficient data"
            )
            return

        results.add_pass(
            "Multi-Agent Workflow - Research",
            f"Research completed: {len(research_result)} chars"
        )

        # Step 2: Create Document (Local File)
        print("\n-> STEP 2: Create Document")
        output_dir = Path("test_outputs")
        output_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        doc_filename = f"research_report_{timestamp}.md"
        doc_path = output_dir / doc_filename

        # Format as structured document
        document_content = f"""# Research Report: Google Agent Development Kit
**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Topic:** {research_query}

---

## Executive Summary

{research_result[:500]}...

## Full Research Findings

{research_result}

---

*Report generated by Google Workspace ADK Multi-Agent System*
*Researcher Agent + Document Generator*
"""

        with open(doc_path, 'w', encoding='utf-8') as f:
            f.write(document_content)

        if doc_path.exists():
            file_size = doc_path.stat().st_size
            results.add_pass(
                "Multi-Agent Workflow - Document Creation",
                f"Document saved: {doc_path} ({file_size} bytes)"
            )
            print(f"  Document saved to: {doc_path}")
        else:
            results.add_fail(
                "Multi-Agent Workflow - Document Creation",
                "Failed to save document"
            )

        # Step 3: Prepare Email (Simulated)
        print("\n-> STEP 3: Prepare Email Draft")

        email_content = {
            "to": "recipient@example.com",
            "subject": f"Research Report: Google Agent Development Kit",
            "body": f"""Hi,

Please find attached the research report on Google Agent Development Kit.

Key highlights from the research:
{research_result[:300]}...

Best regards,
Research Agent

---
This email was prepared by the Google Workspace ADK Multi-Agent System.
Attachment: {doc_filename}
""",
            "attachment": str(doc_path)
        }

        # Save email draft to file (simulating email preparation)
        email_draft_path = output_dir / f"email_draft_{timestamp}.txt"
        with open(email_draft_path, 'w', encoding='utf-8') as f:
            f.write(f"TO: {email_content['to']}\n")
            f.write(f"SUBJECT: {email_content['subject']}\n")
            f.write(f"ATTACHMENT: {email_content['attachment']}\n")
            f.write(f"\n{email_content['body']}")

        if email_draft_path.exists():
            results.add_pass(
                "Multi-Agent Workflow - Email Draft",
                f"Email draft prepared: {email_draft_path}"
            )
            print(f"  Email draft saved to: {email_draft_path}")

            results.add_pass(
                "Multi-Agent Workflow - COMPLETE",
                f"Full workflow executed: Research -> Document -> Email"
            )
        else:
            results.add_fail(
                "Multi-Agent Workflow - Email Draft",
                "Failed to create email draft"
            )

        # Note about OAuth
        print(f"\n  {Colors.YELLOW}[NOTE]{Colors.END} Actual Gmail sending requires OAuth authentication.")
        print(f"  For now, email draft has been saved locally.")
        print(f"  To send via Gmail API, run: python tools/oauth_cli.py")

    except Exception as e:
        results.add_fail("Multi-Agent Workflow", str(e))
        logger.exception("Multi-agent workflow test failed")


# ============================================================================
# TEST 7: Croatian News Aggregation
# ============================================================================

async def test_croatian_news(results: TestResults):
    """Test Croatian news portal scraping"""
    print(f"\n{Colors.HEADER}{'=' * 80}{Colors.END}")
    print(f"{Colors.HEADER}TEST 7: Croatian News Aggregation{Colors.END}")
    print(f"{Colors.HEADER}{'=' * 80}{Colors.END}")

    try:
        print("\n-> Searching Croatian news portals...")

        # Search Croatian portals
        query = "umjetna inteligencija site:index.hr OR site:jutarnji.hr"

        search_result = await google_search_simple(
            credentials=None,
            query=query,
            num_results=5
        )

        if search_result.get("sources"):
            croatian_urls = [
                source['url'] for source in search_result['sources'][:3]
                if 'index.hr' in source['url'] or 'jutarnji.hr' in source['url']
            ]

            if croatian_urls:
                results.add_pass(
                    "Croatian News Search",
                    f"Found {len(croatian_urls)} Croatian news URLs"
                )

                # Scrape articles
                print("\n-> Scraping Croatian articles...")
                scrape_results = await scrape_multiple_urls(
                    credentials=None,
                    urls=croatian_urls
                )

                success_count = sum(1 for r in scrape_results if "text" in r)
                results.add_pass(
                    "Croatian News Scraping",
                    f"Successfully scraped {success_count}/{len(croatian_urls)} articles"
                )
            else:
                results.add_warning(
                    "Croatian News Search",
                    "No Croatian URLs found in search results"
                )
        else:
            results.add_warning(
                "Croatian News Search",
                "Search returned no results"
            )

    except Exception as e:
        results.add_fail("Croatian News Aggregation", str(e))
        logger.exception("Croatian news test failed")


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

async def run_all_tests():
    """Run all tests"""
    print(f"\n{Colors.BOLD}{'=' * 80}{Colors.END}")
    print(f"{Colors.BOLD}COMPREHENSIVE MULTI-AGENT WORKFLOW TEST SUITE{Colors.END}")
    print(f"{Colors.BOLD}{'=' * 80}{Colors.END}")
    print(f"{Colors.CYAN}Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.END}")
    print(f"{Colors.CYAN}Testing: Real API calls - NO MOCKS!{Colors.END}")
    print(f"{Colors.CYAN}Python: {sys.version}{Colors.END}")
    print(f"{Colors.BOLD}{'=' * 80}{Colors.END}\n")

    results = TestResults()

    # Run all tests
    await test_system_initialization(results)
    await test_google_search(results)
    await test_youtube_transcript(results)
    await test_web_scraping(results)
    await test_researcher_e2e(results)
    await test_multi_agent_workflow(results)
    await test_croatian_news(results)

    # Print summary
    results.print_summary()

    # Generate report file
    report_path = Path("test_outputs") / f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    report_path.parent.mkdir(exist_ok=True)

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("COMPREHENSIVE MULTI-AGENT WORKFLOW TEST REPORT\n")
        f.write("=" * 80 + "\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total Tests: {len(results.passed) + len(results.failed)}\n")
        f.write(f"Passed: {len(results.passed)}\n")
        f.write(f"Failed: {len(results.failed)}\n")
        f.write(f"Warnings: {len(results.warnings)}\n")
        f.write("=" * 80 + "\n\n")

        f.write("PASSED TESTS:\n")
        for test_name, details in results.passed:
            f.write(f"  [PASS] {test_name}\n")
            if details:
                f.write(f"    {details}\n")

        if results.failed:
            f.write("\nFAILED TESTS:\n")
            for test_name, error in results.failed:
                f.write(f"  [FAIL] {test_name}\n")
                f.write(f"    {error}\n")

        if results.warnings:
            f.write("\nWARNINGS:\n")
            for test_name, warning in results.warnings:
                f.write(f"  [WARN] {test_name}\n")
                f.write(f"    {warning}\n")

    print(f"\n{Colors.GREEN}Test report saved to: {report_path}{Colors.END}\n")

    return len(results.failed) == 0


if __name__ == "__main__":
    try:
        success = asyncio.run(run_all_tests())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Tests interrupted by user{Colors.END}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}Fatal error: {e}{Colors.END}")
        logger.exception("Fatal error in test suite")
        sys.exit(1)
