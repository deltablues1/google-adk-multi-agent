#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Monitoring Integration

Tests monitoring with real API calls to verify:
1. Structured logging is working
2. Metrics are being collected
3. Cache tracking is operational
4. Agent and tool call tracking works

Test User: tgolic555@gmail.com (Tomislav Golić)
"""

import sys
import os
import asyncio
import logging
from pathlib import Path

# Fix Windows console encoding for emoji
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Setup environment
os.environ['LOG_LEVEL'] = 'DEBUG'

from monitoring.logging_config import setup_logging
from monitoring.metrics import get_metrics_collector, AgentMetrics
from tools.resilience.cache import get_cache_stats
from config.agent_registry import create_agent_instance


# Setup logging
setup_logging(level='DEBUG')
logger = logging.getLogger(__name__)


async def test_agent_with_monitoring(agent_name: str, test_request: str):
    """
    Test a single agent with monitoring

    Args:
        agent_name: Name of agent to test
        test_request: Request to send to agent
    """
    print(f"\n{'='*80}")
    print(f"🧪 TESTING: {agent_name}")
    print(f"📝 Request: {test_request}")
    print('='*80)

    try:
        # Create agent instance
        logger.info(f"Creating agent instance: {agent_name}")
        agent = create_agent_instance(agent_name)

        # Execute request
        logger.info(f"Executing request on {agent_name}")
        result = await agent.run(test_request)

        # Log result
        logger.info(
            f"Agent {agent_name} completed",
            extra={
                "agent_name": agent_name,
                "result_preview": str(result)[:200],
                "success": True
            }
        )

        print(f"\n✅ SUCCESS!")
        print(f"📤 Result Preview: {str(result)[:300]}...")

        return True

    except Exception as e:
        logger.error(
            f"Agent {agent_name} failed",
            extra={
                "agent_name": agent_name,
                "error": str(e),
                "error_type": type(e).__name__
            },
            exc_info=True
        )

        print(f"\n❌ FAILED!")
        print(f"Error: {e}")

        return False


async def main(auto_yes=False):
    """Main test function"""
    print("\n" + "="*80)
    print("📊 MONITORING INTEGRATION TEST")
    print("="*80)
    print("\nThis test will:")
    print("  1. Execute real API calls with monitoring")
    print("  2. Track metrics and logging")
    print("  3. Display comprehensive monitoring data")
    print("\n⚠️  NOTE: This makes REAL API calls to Google services!")
    print("="*80)

    # Confirm before proceeding
    if not auto_yes:
        try:
            response = input("\nProceed with testing? (y/N): ")
            if response.lower() != 'y':
                print("❌ Test cancelled.")
                return
        except EOFError:
            print("\n⚠️  No interactive terminal - proceeding automatically...")
            auto_yes = True

    print("\n🚀 Starting tests...")

    # ========================================================================
    # TEST 1: Simple Gmail Search (READ operation)
    # ========================================================================
    print("\n" + "="*80)
    print("TEST 1: Gmail Search (Mailer Agent)")
    print("="*80)

    success1 = await test_agent_with_monitoring(
        agent_name="mailer",
        test_request="List my last 3 emails from inbox"
    )

    # Wait a bit to see metrics
    await asyncio.sleep(2)

    # ========================================================================
    # TEST 2: Calendar Check (READ operation)
    # ========================================================================
    print("\n" + "="*80)
    print("TEST 2: Calendar Events (Secretary Agent)")
    print("="*80)

    success2 = await test_agent_with_monitoring(
        agent_name="secretary",
        test_request="What events do I have today?"
    )

    await asyncio.sleep(2)

    # ========================================================================
    # TEST 3: Test Cache Hit (Repeat same request)
    # ========================================================================
    print("\n" + "="*80)
    print("TEST 3: Cache Hit Test (Repeat Gmail Search)")
    print("="*80)
    print("⚡ This should hit cache and be much faster!")

    success3 = await test_agent_with_monitoring(
        agent_name="mailer",
        test_request="List my last 3 emails from inbox"  # Same as Test 1
    )

    await asyncio.sleep(1)

    # ========================================================================
    # DISPLAY MONITORING RESULTS
    # ========================================================================
    print("\n" + "="*80)
    print("📊 MONITORING RESULTS")
    print("="*80)

    # Get metrics
    metrics_collector = get_metrics_collector()
    metrics = metrics_collector.get_metrics()

    print("\n🤖 AGENT METRICS:")
    print("-" * 80)
    for key, count in metrics['counters'].items():
        if 'agent_calls' in key:
            print(f"  {key}: {count}")

    print("\n🔧 TOOL CALL METRICS:")
    print("-" * 80)
    for key, count in metrics['counters'].items():
        if 'tool_calls' in key:
            print(f"  {key}: {count}")

    print("\n⏱️  TIMING METRICS:")
    print("-" * 80)
    for key, timing in metrics['timings'].items():
        print(f"  {key}:")
        print(f"    Count: {timing['count']}")
        print(f"    Avg:   {timing['avg']:.3f}s")
        print(f"    Min:   {timing['min']:.3f}s")
        print(f"    Max:   {timing['max']:.3f}s")

    # Cache stats
    print("\n💾 CACHE METRICS:")
    print("-" * 80)
    try:
        cache_stats = get_cache_stats()
        global_stats = cache_stats.get('global', {})

        if global_stats:
            total_requests = global_stats.get('total_hits', 0) + global_stats.get('total_misses', 0)
            print(f"  Total Requests:  {total_requests}")
            print(f"  Cache Hits:      {global_stats.get('total_hits', 0)}")
            print(f"  Cache Misses:    {global_stats.get('total_misses', 0)}")
            print(f"  Hit Rate:        {global_stats.get('hit_rate', 0):.1f}%")
            print(f"  API Calls Saved: {global_stats.get('api_calls_saved', 0)}")

            # Per-service
            print("\n  Per-Service Cache:")
            for service, stats in cache_stats.get('services', {}).items():
                print(f"    {service}:")
                print(f"      Size: {stats.get('size', 0)}/{stats.get('max_size', 0)}")
                print(f"      Hit Rate: {stats.get('hit_rate', 0):.1f}%")
        else:
            print("  No cache activity")

    except Exception as e:
        print(f"  Error getting cache stats: {e}")

    # Cache operations from metrics
    print("\n🔍 CACHE OPERATIONS:")
    print("-" * 80)
    for key, count in metrics['counters'].items():
        if 'cache_operations' in key or 'cache_evictions' in key:
            print(f"  {key}: {count}")

    # Errors
    if metrics['errors']:
        print("\n❌ ERRORS:")
        print("-" * 80)
        for key, count in metrics['errors'].items():
            print(f"  {key}: {count}")

    # ========================================================================
    # SUMMARY
    # ========================================================================
    print("\n" + "="*80)
    print("📈 TEST SUMMARY")
    print("="*80)

    tests_passed = sum([success1, success2, success3])
    total_tests = 3

    print(f"\n  Tests Passed: {tests_passed}/{total_tests}")
    print(f"  Success Rate: {tests_passed/total_tests*100:.1f}%")

    if success1 and success3:
        print("\n  ✅ Cache Test: SUCCESS!")
        print("     - First request should show Cache MISS")
        print("     - Second request should show Cache HIT")
        print("     - Second request should be faster!")
    else:
        print("\n  ⚠️  Cache Test: Check logs for details")

    print("\n" + "="*80)
    print("💡 NEXT STEPS:")
    print("="*80)
    print("\n  1. View detailed metrics:")
    print("     python scripts/show_metrics.py")
    print("\n  2. Watch metrics in real-time:")
    print("     python scripts/show_metrics.py --watch")
    print("\n  3. Check logs:")
    print("     Look for structured JSON logs with extra fields")
    print("\n  4. Run full test suite:")
    print("     pytest tests/integration/ -v -s")
    print("\n" + "="*80)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test monitoring integration")
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='Skip confirmation prompt'
    )

    args = parser.parse_args()

    asyncio.run(main(auto_yes=args.yes))
