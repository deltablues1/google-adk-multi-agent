"""
Simplified Test Runner - Core Workflows Only
Brži test samo najvažnijih funkcionalnosti
"""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import sys
import os

# Fix Windows console encoding for Unicode support
if sys.platform == "win32":
    import codecs
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8')

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import main system
from main import WorkspaceADKSystem

# Test Configuration
USER_EMAIL = "tgolic555@gmail.com"
USER_NAME = "Tomislav Golić"
NEW_CONTACT_NAME = "Davor Golić"
NEW_CONTACT_EMAIL = "davor_golic@hotmail.com"
NEW_CONTACT_PHONE = "0915584072"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

async def run_query(system: WorkspaceADKSystem, query: str, description: str):
    """Run single query and print result"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*80}{Colors.RESET}")
    print(f"{Colors.CYAN}🧪 TEST: {description}{Colors.RESET}")
    print(f"{Colors.YELLOW}Query: {query}{Colors.RESET}")
    print(f"{Colors.BLUE}{'─'*80}{Colors.RESET}")

    try:
        print(f"{Colors.CYAN}⏳ Executing...{Colors.RESET}\n")
        response = await system.orchestrator_helper.run(query)

        print(f"\n{Colors.GREEN}✅ SUCCESS{Colors.RESET}")
        print(f"{Colors.BOLD}Response:{Colors.RESET}")
        print(response)

    except Exception as e:
        print(f"\n{Colors.RED}❌ FAILED: {str(e)}{Colors.RESET}")
        import traceback
        traceback.print_exc()

    print(f"{Colors.BLUE}{'='*80}{Colors.RESET}\n")
    await asyncio.sleep(1)  # Small delay between tests

async def main():
    """Run simplified test suite"""

    print(f"""
{Colors.BOLD}{Colors.CYAN}
╔═══════════════════════════════════════════════════════════════╗
║         SIMPLIFIED TEST SUITE - CORE WORKFLOWS                ║
║                                                               ║
║  User: {USER_NAME:<55} ║
║  Email: {USER_EMAIL:<54} ║
╚═══════════════════════════════════════════════════════════════╝
{Colors.RESET}
""")

    # Initialize the system
    print(f"{Colors.CYAN}🔧 Initializing Google Workspace ADK System...{Colors.RESET}\n")
    system = WorkspaceADKSystem()
    system.initialize_agents()

    if not system.verify_authentication():
        print(f"{Colors.RED}❌ Authentication failed. Please check your .env configuration.{Colors.RESET}")
        return

    print(f"\n{Colors.GREEN}✅ System initialized successfully!{Colors.RESET}")
    print(f"{Colors.CYAN}   • {len(system.worker_agents)} worker agents loaded{Colors.RESET}")
    print(f"{Colors.CYAN}   • Orchestrator ready{Colors.RESET}\n")

    # Calculate dates
    today = datetime.now()
    tomorrow = today + timedelta(days=1)
    next_friday = today + timedelta(days=(4 - today.weekday()) % 7)

    tomorrow_str = tomorrow.strftime("%Y-%m-%d")
    friday_str = next_friday.strftime("%Y-%m-%d")

    print(f"{Colors.YELLOW}📅 Dates for testing:{Colors.RESET}")
    print(f"  Today: {today.strftime('%Y-%m-%d %A')}")
    print(f"  Tomorrow: {tomorrow_str} {tomorrow.strftime('%A')}")
    print(f"  Next Friday: {friday_str}")
    print()

    # ============================================================================
    # CORE TESTS - Najvažniji Workflowi
    # ============================================================================

    # 1. Single-Agent: Mailer
    await run_query(
        system=system,
        query="Pokaži mi zadnjih 5 emailova",
        description="Single-Agent: Mailer - Get Recent Emails"
    )

    # 2. Single-Agent: Secretary
    await run_query(
        system=system,
        query="Koja mi je prva obaveza danas?",
        description="Single-Agent: Secretary - Today's First Event"
    )

    # 3. Single-Agent: Rolodex (Search)
    await run_query(
        system=system,
        query=f"Pronađi kontakt {USER_NAME}",
        description="Single-Agent: Rolodex - Find Existing Contact"
    )

    # 4. Single-Agent: Rolodex (Add New)
    await run_query(
        system=system,
        query=f"Dodaj novi kontakt: Ime '{NEW_CONTACT_NAME}', email '{NEW_CONTACT_EMAIL}', telefon '{NEW_CONTACT_PHONE}'",
        description="Single-Agent: Rolodex - Add New Contact"
    )

    # 5. Single-Agent: Tracker
    await run_query(
        system=system,
        query=f"Dodaj zadatak 'Test zadatak iz automation script' do {friday_str}",
        description="Single-Agent: Tracker - Add Task"
    )

    # 6. Single-Agent: Librarian
    await run_query(
        system=system,
        query="Pronađi sve PDF dokumente u mom Drive-u",
        description="Single-Agent: Librarian - Find PDFs"
    )

    # 7. Single-Agent: Researcher
    await run_query(
        system=system,
        query="Istraži Claude API pricing 2026",
        description="Single-Agent: Researcher - Web Research"
    )

    # 8. Multi-Agent: Contact → Email
    await run_query(
        system=system,
        query=f"Pronađi kontakt {USER_NAME} i pošalji mu kratki email sa porukom 'Test iz automation script - {datetime.now().strftime('%H:%M:%S')}'",
        description="Multi-Agent: Rolodex → Mailer"
    )

    # 9. Multi-Agent: Research → Email
    await run_query(
        system=system,
        query=f"Istraži Claude Sonnet 4.5 features i pošalji kratak sažetak na {USER_EMAIL}",
        description="Multi-Agent: Researcher → Mailer"
    )

    # 10. Multi-Agent: Calendar → Tasks
    await run_query(
        system=system,
        query=f"Pronađi sve sastanke za sutra ({tomorrow_str}) i stvori zadatke za pripremu",
        description="Multi-Agent: Secretary → Tracker"
    )

    # 11. Croatian Support: Date Format
    await run_query(
        system=system,
        query=f"Dodaj zadatak 'Završiti godišnji izvještaj' do {friday_str}",
        description="Croatian Support: Character Preservation (č, š, ž)"
    )

    # 12. Error Handling: Invalid Email
    await run_query(
        system=system,
        query="Pošalji email na 'invalid_bez_at' sa porukom 'test'",
        description="Error Handling: Invalid Email Detection"
    )

    # 13. Complex Workflow: Research → Document → Email
    await run_query(
        system=system,
        query=f"Istraži Python async/await best practices, napiši kratki dokument sa sažetkom, i pošalji na {USER_EMAIL}",
        description="Complex Workflow: Researcher → Scribe → Mailer (3 agents)"
    )

    # Final Summary
    print(f"""
{Colors.BOLD}{Colors.GREEN}
╔═══════════════════════════════════════════════════════════════╗
║                    TESTS COMPLETED                            ║
║                                                               ║
║  Check the console output above for results                  ║
║  All tests executed with real data                           ║
╚═══════════════════════════════════════════════════════════════╝
{Colors.RESET}
""")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}⚠️  Tests interrupted by user{Colors.RESET}")
    except Exception as e:
        print(f"\n{Colors.RED}❌ Fatal error: {e}{Colors.RESET}")
        import traceback
        traceback.print_exc()
