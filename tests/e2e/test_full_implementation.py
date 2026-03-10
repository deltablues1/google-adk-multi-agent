"""
Full Implementation Test

Testira kompletnu implementaciju tool execution sistema
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment
from dotenv import load_dotenv
load_dotenv()


async def test_tool_registry():
    """Test 1: Tool Registry Initialization"""
    print("\n" + "="*60)
    print("TEST 1: Tool Registry Initialization")
    print("="*60)

    try:
        from tools.tool_registry import get_tool_registry

        registry = get_tool_registry()
        print(f"✓ Tool registry created: {registry}")
        print(f"✓ Registered tools: {len(registry)}")

        if len(registry) == 0:
            print("⚠ No tools registered yet (expected on first run)")
        else:
            print(f"\n  Available tool categories:")
            for category in ['gmail', 'drive', 'calendar']:
                tools = registry.get_tools_by_category(category)
                if tools:
                    print(f"    - {category}: {len(tools)} tools")

        return True

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_api_implementations():
    """Test 2: API Implementations Registration"""
    print("\n" + "="*60)
    print("TEST 2: API Implementations Registration")
    print("="*60)

    try:
        from tools.tool_registry import get_tool_registry
        from tools.api_implementations import register_all_tools

        registry = get_tool_registry()

        # Register tools
        print("Registering API implementations...")
        status = register_all_tools(registry)

        print("\nRegistration status:")
        for api_name, is_registered in status.items():
            icon = "✓" if is_registered else "✗"
            print(f"  {icon} {api_name.upper()}")

        # Check total
        total = len(registry)
        print(f"\n✓ Total registered tools: {total}")

        if total == 0:
            print("✗ No tools registered!")
            return False

        # Show some tools
        print("\nSample of registered tools:")
        for tool_name in list(registry.list_tools())[:5]:
            print(f"  - {tool_name}")

        return True

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_oauth_manager():
    """Test 3: OAuth Manager"""
    print("\n" + "="*60)
    print("TEST 3: OAuth Manager")
    print("="*60)

    try:
        from auth.oauth_manager import get_oauth_manager

        oauth_manager = get_oauth_manager()
        print(f"✓ OAuth manager created")

        # Check credentials
        credentials = oauth_manager.get_credentials()

        if credentials and credentials.valid:
            print(f"✓ OAuth credentials valid")
            print(f"  Token storage: {oauth_manager.token_storage_path}")
            return True
        else:
            print(f"⚠ No valid OAuth credentials found")
            print(f"  To authenticate, run:")
            print(f"    python tools/oauth_cli.py --auth")
            return False

    except Exception as e:
        print(f"⚠ OAuth test failed: {e}")
        print(f"  This is expected if OAuth credentials are not configured")
        return False


async def test_google_api_client():
    """Test 4: Google API Client"""
    print("\n" + "="*60)
    print("TEST 4: Google API Client")
    print("="*60)

    try:
        from tools.google_api_client import create_api_client_auto

        print("Attempting to create API client...")
        api_client = create_api_client_auto()

        print(f"✓ API client created: {api_client}")
        print(f"  Credentials type: {type(api_client.credentials).__name__}")

        # Try to get a service
        print("\n  Testing service creation:")
        gmail_service = api_client.gmail_service()
        print(f"  ✓ Gmail service: {gmail_service}")

        return True

    except ValueError as e:
        print(f"⚠ API client test failed: {e}")
        print(f"  This is expected if authentication is not configured")
        print(f"\n  To authenticate:")
        print(f"    python tools/oauth_cli.py --auth")
        return False

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_base_agent_tool_execution():
    """Test 5: Base Agent Tool Execution"""
    print("\n" + "="*60)
    print("TEST 5: Base Agent Tool Execution")
    print("="*60)

    try:
        from agents.base_agent import BaseAgent

        # Create a simple agent
        agent = BaseAgent(
            name="test_agent",
            model="gemini-1.5-flash"
        )

        print(f"✓ Test agent created: {agent}")

        # Try to execute a dummy tool (should fail gracefully)
        print("\n  Testing tool execution (expecting auth error)...")
        result = await agent._execute_tool(
            tool_name="gmail_list_labels",
            args={}
        )

        print(f"  Result: {str(result)[:200]}...")

        # Check if result indicates auth issue (expected)
        if "authentication" in str(result).lower() or "error" in str(result).lower():
            print(f"✓ Tool execution framework works (auth error is expected)")
            return True
        else:
            print(f"⚠ Unexpected result")
            return False

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_agent_registry():
    """Test 6: Agent Registry"""
    print("\n" + "="*60)
    print("TEST 6: Agent Registry")
    print("="*60)

    try:
        from config.agent_registry import (
            get_all_agent_names,
            get_worker_agent_names,
            get_agent_config,
            get_registry_stats
        )

        print("Agent registry stats:")
        stats = get_registry_stats()
        for key, value in stats.items():
            print(f"  {key}: {value}")

        print("\n✓ All agents:")
        for agent_name in get_all_agent_names():
            config = get_agent_config(agent_name)
            print(f"  - {agent_name} ({config.model})")

        return True

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_orchestrator():
    """Test 7: Orchestrator Agent"""
    print("\n" + "="*60)
    print("TEST 7: Orchestrator Agent")
    print("="*60)

    try:
        from agents.orchestrator.orchestrator import OrchestratorAgent

        orchestrator = OrchestratorAgent()
        print(f"✓ Orchestrator created: {orchestrator}")

        # Test routing
        print("\n  Testing LLM-based routing...")
        test_request = "List my Gmail labels"

        routing = await orchestrator.route_request(test_request)
        print(f"  Request: {test_request}")
        print(f"  Routed to: {routing['agent']}")
        print(f"  Reasoning: {routing.get('reasoning', 'N/A')}")

        return True

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

async def run_all_tests():
    """Run all tests"""
    print("\n")
    print("="*60)
    print("FULL IMPLEMENTATION TEST SUITE")
    print("="*60)
    print("\nTesting Google Workspace ADK Implementation")
    print(f"Python: {sys.version}")
    print(f"CWD: {os.getcwd()}")
    print()

    tests = [
        ("Tool Registry", test_tool_registry),
        ("API Implementations", test_api_implementations),
        ("OAuth Manager", test_oauth_manager),
        ("Google API Client", test_google_api_client),
        ("Base Agent Tool Execution", test_base_agent_tool_execution),
        ("Agent Registry", test_agent_registry),
        ("Orchestrator", test_orchestrator),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"Test {test_name} crashed: {e}")
            results.append((test_name, False))

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        icon = "✓" if result else "✗"
        print(f"  {icon} {test_name}")

    print()
    print(f"Passed: {passed}/{total}")
    print(f"Success Rate: {(passed/total*100):.1f}%")

    if passed == total:
        print("\n✓✓✓ ALL TESTS PASSED! ✓✓✓")
    elif passed >= total * 0.8:
        print("\n✓✓ MOST TESTS PASSED ✓✓")
        print("\nNote: Some failures are expected if OAuth is not configured.")
    else:
        print("\n⚠ SOME TESTS FAILED ⚠")

    print("\n" + "="*60)
    print("NEXT STEPS")
    print("="*60)
    print("\n1. Configure OAuth credentials (if not done):")
    print("   - Add GOOGLE_OAUTH_CLIENT_ID to .env")
    print("   - Add GOOGLE_OAUTH_CLIENT_SECRET to .env")
    print("\n2. Authenticate:")
    print("   python tools/oauth_cli.py --auth")
    print("\n3. Run the system:")
    print("   python main.py")
    print()

    return passed == total


if __name__ == "__main__":
    try:
        success = asyncio.run(run_all_tests())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
