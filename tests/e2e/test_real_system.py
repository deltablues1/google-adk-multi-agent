#!/usr/bin/env python3
"""
Real System Integration Test
Testira stvarni multi-agent sustav s pravim konfiguracijama
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()

# Import sistema
from config.agent_registry import (
    get_worker_agent_names,
    create_agent_instance,
    get_registry_stats,
    AGENT_REGISTRY
)
from config.auth_config import get_auth_config
from agents.orchestrator.orchestrator import OrchestratorAgent


class SystemTester:
    """Testira pravi multi-agent sistem"""

    def __init__(self):
        self.orchestrator = None
        self.worker_agents = []
        self.auth_config = get_auth_config()
        self.test_results = {
            'passed': [],
            'failed': [],
            'warnings': []
        }

    def log_test(self, test_name: str, passed: bool, message: str = ""):
        """Logira rezultat testa"""
        if passed:
            logger.info(f"✓ TEST PASSED: {test_name} {message}")
            self.test_results['passed'].append(test_name)
        else:
            logger.error(f"✗ TEST FAILED: {test_name} {message}")
            self.test_results['failed'].append(test_name)

    def log_warning(self, test_name: str, message: str):
        """Logira upozorenje"""
        logger.warning(f"⚠ WARNING: {test_name} - {message}")
        self.test_results['warnings'].append((test_name, message))

    def test_environment(self):
        """Test 1: Environment Configuration"""
        logger.info("\n" + "="*60)
        logger.info("TEST 1: Environment Configuration")
        logger.info("="*60)

        # Required env vars
        required_vars = [
            'GOOGLE_CLOUD_PROJECT',
            'GOOGLE_OAUTH_CLIENT_ID',
            'GOOGLE_OAUTH_CLIENT_SECRET',
            'GEMINI_MODEL_FLASH',
            'GEMINI_MODEL_PRO',
            'SESSION_STORAGE'
        ]

        all_present = True
        for var in required_vars:
            value = os.getenv(var)
            if value:
                logger.info(f"  ✓ {var}: {value[:30]}..." if len(value) > 30 else f"  ✓ {var}: {value}")
            else:
                logger.error(f"  ✗ {var}: MISSING")
                all_present = False

        self.log_test("Environment Variables", all_present)

        # Check credential files
        cred_files = [
            'service_account_key.json',
            'oauth_client_credentials.json'
        ]

        for file in cred_files:
            if os.path.exists(file):
                logger.info(f"  ✓ Credential file exists: {file}")
            else:
                logger.warning(f"  ⚠ Credential file missing: {file}")

        return all_present

    def test_agent_registry(self):
        """Test 2: Agent Registry"""
        logger.info("\n" + "="*60)
        logger.info("TEST 2: Agent Registry")
        logger.info("="*60)

        try:
            stats = get_registry_stats()
            logger.info(f"  Total agents: {stats['total_agents']}")
            logger.info(f"  Worker agents: {stats['worker_agents']}")
            logger.info(f"  Flash agents: {stats['flash_agents']}")
            logger.info(f"  Pro agents: {stats['pro_agents']}")

            # Verify all agents registered
            expected_agents = [
                'orchestrator', 'mailer', 'librarian', 'scribe',
                'analyst', 'secretary', 'rolodex', 'tracker',
                'researcher', 'scraper', 'synthesizer', 'expense'
            ]

            all_registered = all(name in AGENT_REGISTRY for name in expected_agents)

            if all_registered:
                logger.info(f"  ✓ All {len(expected_agents)} agents registered")
            else:
                missing = [name for name in expected_agents if name not in AGENT_REGISTRY]
                logger.error(f"  ✗ Missing agents: {missing}")

            self.log_test("Agent Registry", all_registered)
            return all_registered

        except Exception as e:
            logger.error(f"  ✗ Registry error: {e}")
            self.log_test("Agent Registry", False, str(e))
            return False

    def test_agent_initialization(self):
        """Test 3: Agent Initialization"""
        logger.info("\n" + "="*60)
        logger.info("TEST 3: Agent Initialization")
        logger.info("="*60)

        worker_names = get_worker_agent_names()
        logger.info(f"  Loading {len(worker_names)} worker agents...")

        initialized_count = 0
        for agent_name in worker_names:
            try:
                agent = create_agent_instance(agent_name)
                self.worker_agents.append(agent)
                logger.info(f"  ✓ {agent_name} initialized ({agent.model})")
                initialized_count += 1
            except Exception as e:
                logger.error(f"  ✗ {agent_name} failed: {e}")

        success = initialized_count == len(worker_names)
        self.log_test("Agent Initialization", success, f"{initialized_count}/{len(worker_names)}")

        # Initialize Orchestrator
        try:
            logger.info("  Creating Orchestrator...")
            self.orchestrator = OrchestratorAgent(sub_agents=self.worker_agents)
            logger.info(f"  ✓ Orchestrator initialized with {len(self.worker_agents)} sub-agents")
            self.log_test("Orchestrator Initialization", True)
        except Exception as e:
            logger.error(f"  ✗ Orchestrator failed: {e}")
            self.log_test("Orchestrator Initialization", False, str(e))
            return False

        return success

    def test_authentication(self):
        """Test 4: Authentication Configuration"""
        logger.info("\n" + "="*60)
        logger.info("TEST 4: Authentication")
        logger.info("="*60)

        # OAuth check
        oauth_configured = bool(
            self.auth_config.oauth.client_id and
            self.auth_config.oauth.client_secret
        )

        logger.info(f"  OAuth Client ID: {self.auth_config.oauth.client_id[:30] if self.auth_config.oauth.client_id else 'MISSING'}...")
        logger.info(f"  OAuth configured: {oauth_configured}")

        # Service Account check
        sa_configured = bool(
            self.auth_config.service_account.credentials_file and
            os.path.exists(self.auth_config.service_account.credentials_file)
        )

        logger.info(f"  Service Account file: {self.auth_config.service_account.credentials_file}")
        logger.info(f"  Service Account configured: {sa_configured}")

        has_auth = oauth_configured or sa_configured

        if has_auth:
            logger.info("  ✓ At least one authentication method configured")
        else:
            logger.error("  ✗ No authentication method configured")

        self.log_test("Authentication", has_auth)
        return has_auth

    async def test_agent_routing(self):
        """Test 5: Agent Routing Logic"""
        logger.info("\n" + "="*60)
        logger.info("TEST 5: Agent Routing Logic")
        logger.info("="*60)

        # Test requests for different agents
        test_cases = [
            ("Send an email to john@example.com", "mailer", "Email request should route to mailer"),
            ("Find files in my Drive", "librarian", "Drive request should route to librarian"),
            ("Create a Google Doc", "scribe", "Docs request should route to scribe"),
            ("Analyze spreadsheet data", "analyst", "Sheets request should route to analyst"),
            ("Show my calendar", "secretary", "Calendar request should route to secretary"),
            ("List my contacts", "rolodex", "Contacts request should route to rolodex"),
            ("Create a task", "tracker", "Tasks request should route to tracker"),
            ("Research topic X", "researcher", "Research request should route to researcher"),
            ("Summarize these research notes", "synthesizer", "Synthesis request should route to synthesizer"),
            ("Process this receipt image", "expense", "Receipt request should route to expense"),
            ("What is 2+2?", "self", "Simple query should be handled by orchestrator"),
        ]

        passed = 0
        for request, expected_agent, description in test_cases:
            try:
                routing = await self.orchestrator.route_request(request)
                actual_agent = routing.get('agent', 'unknown')

                if actual_agent == expected_agent:
                    logger.info(f"  ✓ '{request[:40]}...' -> {actual_agent}")
                    passed += 1
                else:
                    logger.warning(f"  ⚠ '{request[:40]}...' -> {actual_agent} (expected: {expected_agent})")
                    self.log_warning("Routing", f"{description}: got {actual_agent}")
            except Exception as e:
                logger.error(f"  ✗ '{request[:40]}...' -> ERROR: {e}")

        success = passed >= len(test_cases) * 0.7  # 70% success rate
        self.log_test("Agent Routing", success, f"{passed}/{len(test_cases)} correct")
        return success

    def test_agent_availability(self):
        """Test 6: Agent Availability"""
        logger.info("\n" + "="*60)
        logger.info("TEST 6: Agent Availability")
        logger.info("="*60)

        agent_names = ['mailer', 'librarian', 'scribe', 'analyst', 'secretary', 'rolodex', 'tracker', 'researcher', 'scraper', 'synthesizer', 'expense']

        available = 0
        for name in agent_names:
            agent = self.orchestrator.get_sub_agent(name)
            if agent:
                logger.info(f"  ✓ {name} available")
                available += 1
            else:
                logger.error(f"  ✗ {name} NOT available")

        success = available == len(agent_names)
        self.log_test("Agent Availability", success, f"{available}/{len(agent_names)}")
        return success

    def test_credentials_store(self):
        """Test 7: Credentials Store"""
        logger.info("\n" + "="*60)
        logger.info("TEST 7: Credentials Store")
        logger.info("="*60)

        try:
            from auth.credential_store import get_credential_store

            store = get_credential_store()
            auth_type = store.get_auth_type()

            logger.info(f"  Auth type detected: {auth_type}")

            if auth_type == 'none':
                logger.warning("  ⚠ No credentials available (OAuth flow may be needed)")
                self.log_warning("Credentials", "No credentials available - OAuth flow will be needed on first use")
                # This is OK for first run
                return True
            else:
                logger.info(f"  ✓ Credentials available ({auth_type})")
                self.log_test("Credentials Store", True, f"Type: {auth_type}")
                return True

        except Exception as e:
            logger.error(f"  ✗ Credentials store error: {e}")
            self.log_test("Credentials Store", False, str(e))
            return False

    def print_summary(self):
        """Ispisuje sažetak testova"""
        logger.info("\n" + "="*60)
        logger.info("TEST SUMMARY")
        logger.info("="*60)

        total = len(self.test_results['passed']) + len(self.test_results['failed'])
        passed = len(self.test_results['passed'])
        failed = len(self.test_results['failed'])
        warnings = len(self.test_results['warnings'])

        logger.info(f"\nTotal tests: {total}")
        logger.info(f"✓ Passed: {passed}")
        logger.info(f"✗ Failed: {failed}")
        logger.info(f"⚠ Warnings: {warnings}")

        if failed > 0:
            logger.info("\nFailed tests:")
            for test in self.test_results['failed']:
                logger.info(f"  - {test}")

        if warnings > 0:
            logger.info("\nWarnings:")
            for test, msg in self.test_results['warnings']:
                logger.info(f"  - {test}: {msg}")

        success_rate = (passed / total * 100) if total > 0 else 0
        logger.info(f"\nSuccess rate: {success_rate:.1f}%")

        if success_rate >= 80:
            logger.info("\n✓✓✓ SYSTEM READY FOR USE! ✓✓✓")
            logger.info("\nNext steps:")
            logger.info("  1. Run: python main.py")
            logger.info("  2. Type: List my last 5 emails")
            logger.info("  3. Follow OAuth authorization flow when prompted")
        elif success_rate >= 60:
            logger.info("\n⚠⚠⚠ SYSTEM PARTIALLY READY ⚠⚠⚠")
            logger.info("Some issues detected but system should work with limitations.")
        else:
            logger.info("\n✗✗✗ SYSTEM NOT READY ✗✗✗")
            logger.info("Critical issues detected. Review failed tests above.")

        return success_rate >= 80

    async def run_all_tests(self):
        """Pokreće sve testove"""
        logger.info("\n" + "#"*60)
        logger.info("# GOOGLE WORKSPACE ADK - SYSTEM INTEGRATION TEST")
        logger.info("#"*60)

        try:
            # Run all tests
            self.test_environment()
            self.test_agent_registry()
            self.test_agent_initialization()
            self.test_authentication()
            self.test_credentials_store()
            self.test_agent_availability()
            await self.test_agent_routing()

            # Print summary
            return self.print_summary()

        except Exception as e:
            logger.error(f"\nFATAL ERROR during testing: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    """Main entry point"""
    tester = SystemTester()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
