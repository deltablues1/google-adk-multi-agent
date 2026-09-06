"""
Test Cloud Logging Implementation
==================================

Simple test to verify Cloud Logging is working
"""

import os
import sys
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

async def test_monitoring():
    """Test monitoring with a simple agent request"""
    print("\n" + "="*80)
    print("  🧪 Testing Cloud Logging Implementation")
    print("="*80)

    print(f"\n📋 Configuration:")
    print(f"   Project: {os.getenv('GOOGLE_CLOUD_PROJECT')}")
    print(f"   Cloud Logging: {os.getenv('USE_CLOUD_LOGGING')}")
    print(f"   Log Level: {os.getenv('LOG_LEVEL')}")

    # Import system
    from config.agent_registry import create_agent_instance
    from agents.orchestrator.orchestrator import OrchestratorAgent
    from tools.initialize_tools import ensure_tools_initialized

    print(f"\n🔧 Initializing system...")

    # Initialize tools
    ensure_tools_initialized()

    # Create researcher agent
    researcher = create_agent_instance('researcher')

    # Create orchestrator
    orchestrator = OrchestratorAgent(sub_agents=[researcher])

    print(f"\n✅ System initialized")
    print(f"\n🚀 Executing test request...")
    print(f"   Request: 'Što je Google Cloud Monitoring?'")
    print(f"\n   This will:")
    print(f"   1. Generate a session_id")
    print(f"   2. Log to Cloud Logging")
    print(f"   3. Execute the agent")
    print(f"   4. Log completion with metrics\n")

    # Execute request
    result = await orchestrator.execute("Što je Google Cloud Monitoring?")

    print(f"\n" + "="*80)
    print(f"  ✅ TEST COMPLETE")
    print(f"="*80)

    print(f"\n📊 Result Preview:")
    print(f"   {result[:200]}...")

    print(f"\n📋 Next Steps:")
    print(f"\n1. Check Cloud Logging:")
    print(f"   https://console.cloud.google.com/logs?project={os.getenv('GOOGLE_CLOUD_PROJECT')}")

    print(f"\n2. Filter by log name:")
    print(f'   logName="projects/{os.getenv('GOOGLE_CLOUD_PROJECT')}/logs/adk-agent-system"')

    print(f"\n3. Look for fields:")
    print(f"   • jsonPayload.session_id")
    print(f"   • jsonPayload.agent_name")
    print(f"   • jsonPayload.event_type")
    print(f"   • jsonPayload.duration_ms")

    print(f"\n4. Try this query:")
    print(f'   jsonPayload.event_type="agent_request_success"')

    print(f"\n✅ If you see logs with these fields, monitoring is working!")
    print(f"\n")


if __name__ == "__main__":
    # Windows console encoding, only when this file is run as a script.
    #
    # It used to happen at import time, which meant it happened under pytest
    # too: rebinding sys.stdout out from under pytest's capture broke the
    # capture teardown, and the failure took the whole session with it. Every
    # test in tests/integration collected and none of them ran — for as long
    # as anyone had been reading the CI output.
    if sys.platform == "win32":
        import io as _io

        sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    asyncio.run(test_monitoring())
