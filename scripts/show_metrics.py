#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick Metrics Dashboard

Shows real-time metrics for monitoring system performance.
Usage:
    python scripts/show_metrics.py           # One-time display
    python scripts/show_metrics.py --watch   # Continuous display (every 5s)
"""

import sys
import os
import time
from pathlib import Path

# Fix Windows console encoding for emoji
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from monitoring.metrics import get_metrics_collector
from tools.resilience.cache import get_cache_stats


def format_duration(seconds):
    """Format duration in human-readable format"""
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.2f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"


def format_number(num):
    """Format large numbers with commas"""
    return f"{num:,}"


def show_metrics():
    """Display current metrics"""
    print("\n" + "="*80)
    print("📊 AGENT SYSTEM METRICS DASHBOARD")
    print("="*80)
    print(f"⏰ Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    # Get metrics from collector
    metrics_collector = get_metrics_collector()
    metrics = metrics_collector.get_metrics()

    # ========================================================================
    # AGENT METRICS
    # ========================================================================
    print("\n🤖 AGENT METRICS")
    print("-" * 80)

    agent_calls = {}
    tool_calls = {}

    for key, count in metrics['counters'].items():
        if 'agent_calls' in key:
            # Parse agent name and success status
            # Format: agent_calls[agent=mailer,success=True]
            parts = key.split('[')[1].rstrip(']').split(',')
            agent_info = {p.split('=')[0]: p.split('=')[1] for p in parts}
            agent_name = agent_info.get('agent', 'unknown')
            success = agent_info.get('success', 'unknown')

            if agent_name not in agent_calls:
                agent_calls[agent_name] = {'success': 0, 'failure': 0}

            if success == 'True':
                agent_calls[agent_name]['success'] += count
            else:
                agent_calls[agent_name]['failure'] += count

        elif 'tool_calls' in key:
            # Parse tool call info
            parts = key.split('[')[1].rstrip(']').split(',')
            tool_info = {p.split('=')[0]: p.split('=')[1] for p in parts}
            agent_name = tool_info.get('agent', 'unknown')
            tool_name = tool_info.get('tool', 'unknown')
            success = tool_info.get('success', 'unknown')

            tool_key = f"{agent_name}:{tool_name}"
            if tool_key not in tool_calls:
                tool_calls[tool_key] = {'success': 0, 'failure': 0}

            if success == 'True':
                tool_calls[tool_key]['success'] += count
            else:
                tool_calls[tool_key]['failure'] += count

    if agent_calls:
        print(f"\n  {'Agent':<20} {'Success':<10} {'Failure':<10} {'Total':<10} {'Success Rate':<15}")
        print("  " + "-"*75)
        for agent, stats in sorted(agent_calls.items()):
            total = stats['success'] + stats['failure']
            success_rate = (stats['success'] / total * 100) if total > 0 else 0
            print(f"  {agent:<20} {stats['success']:<10} {stats['failure']:<10} {total:<10} {success_rate:>6.1f}%")
    else:
        print("  No agent calls yet")

    # ========================================================================
    # TOOL CALL METRICS
    # ========================================================================
    if tool_calls:
        print("\n🔧 TOOL CALL METRICS")
        print("-" * 80)
        print(f"  {'Tool (Agent:Tool)':<40} {'Success':<10} {'Failure':<10} {'Success Rate':<15}")
        print("  " + "-"*75)
        for tool_key, stats in sorted(tool_calls.items()):
            total = stats['success'] + stats['failure']
            success_rate = (stats['success'] / total * 100) if total > 0 else 0
            display_key = tool_key[:38] + ".." if len(tool_key) > 40 else tool_key
            print(f"  {display_key:<40} {stats['success']:<10} {stats['failure']:<10} {success_rate:>6.1f}%")

    # ========================================================================
    # TIMING METRICS
    # ========================================================================
    if metrics['timings']:
        print("\n⏱️  TIMING METRICS")
        print("-" * 80)
        print(f"  {'Operation':<40} {'Count':<8} {'Avg':<10} {'Min':<10} {'Max':<10}")
        print("  " + "-"*78)
        for key, timing in sorted(metrics['timings'].items()):
            if timing['count'] > 0:
                display_key = key[:38] + ".." if len(key) > 40 else key
                print(
                    f"  {display_key:<40} "
                    f"{timing['count']:<8} "
                    f"{format_duration(timing['avg']):<10} "
                    f"{format_duration(timing['min']):<10} "
                    f"{format_duration(timing['max']):<10}"
                )

    # ========================================================================
    # CACHE METRICS
    # ========================================================================
    try:
        cache_stats = get_cache_stats()

        print("\n💾 CACHE METRICS")
        print("-" * 80)

        # Global stats
        global_stats = cache_stats.get('global', {})
        if global_stats:
            total_requests = global_stats.get('total_hits', 0) + global_stats.get('total_misses', 0)
            hit_rate = global_stats.get('hit_rate', 0)
            api_calls_saved = global_stats.get('api_calls_saved', 0)

            print(f"\n  Global Cache Stats:")
            print(f"    Total Requests:  {format_number(total_requests)}")
            print(f"    Cache Hits:      {format_number(global_stats.get('total_hits', 0))}")
            print(f"    Cache Misses:    {format_number(global_stats.get('total_misses', 0))}")
            print(f"    Hit Rate:        {hit_rate:.1f}%")
            print(f"    API Calls Saved: {format_number(api_calls_saved)}")

            # Estimated cost savings (assuming $0.0004 per API call)
            cost_saved = api_calls_saved * 0.0004
            print(f"    Cost Savings:    ${cost_saved:.2f}")

        # Per-service stats
        service_stats = cache_stats.get('services', {})
        if service_stats:
            print(f"\n  Per-Service Cache Stats:")
            print(f"    {'Service':<15} {'Size':<12} {'Hits':<8} {'Misses':<8} {'Hit Rate':<10}")
            print(f"    {'-'*60}")

            for service, stats in sorted(service_stats.items()):
                cache_size = f"{stats.get('size', 0)}/{stats.get('max_size', 0)}"
                hit_rate = stats.get('hit_rate', 0)
                hits = stats.get('hits', 0)
                misses = stats.get('misses', 0)

                print(
                    f"    {service:<15} "
                    f"{cache_size:<12} "
                    f"{hits:<8} "
                    f"{misses:<8} "
                    f"{hit_rate:>6.1f}%"
                )
        else:
            print("  No cache activity yet")

    except Exception as e:
        print(f"\n  Cache stats unavailable: {e}")

    # ========================================================================
    # ERROR METRICS
    # ========================================================================
    if metrics['errors']:
        print("\n❌ ERROR METRICS")
        print("-" * 80)
        print(f"  {'Error Type':<50} {'Count':<10}")
        print("  " + "-"*60)
        for error_key, count in sorted(metrics['errors'].items(), key=lambda x: x[1], reverse=True):
            display_key = error_key[:48] + ".." if len(error_key) > 50 else error_key
            print(f"  {display_key:<50} {count:<10}")

    # ========================================================================
    # CACHE OPERATIONS
    # ========================================================================
    cache_ops = {k: v for k, v in metrics['counters'].items() if 'cache_operations' in k}
    if cache_ops:
        print("\n🔍 CACHE OPERATIONS")
        print("-" * 80)
        print(f"  {'Operation':<50} {'Count':<10}")
        print("  " + "-"*60)
        for op_key, count in sorted(cache_ops.items(), key=lambda x: x[1], reverse=True):
            # Parse operation details
            if '[' in op_key:
                parts = op_key.split('[')[1].rstrip(']').split(',')
                op_info = {p.split('=')[0]: p.split('=')[1] for p in parts}
                operation = op_info.get('operation', 'unknown')
                result = op_info.get('result', '')
                display = f"{operation} - {result}" if result else operation
            else:
                display = op_key

            display_key = display[:48] + ".." if len(display) > 50 else display
            print(f"  {display_key:<50} {count:<10}")

    # ========================================================================
    # SUMMARY
    # ========================================================================
    print("\n" + "="*80)
    total_calls = sum(stats['success'] + stats['failure'] for stats in agent_calls.values())
    total_success = sum(stats['success'] for stats in agent_calls.values())
    overall_success_rate = (total_success / total_calls * 100) if total_calls > 0 else 0

    print(f"📈 SUMMARY:")
    print(f"   Total Agent Calls: {format_number(total_calls)}")
    print(f"   Overall Success Rate: {overall_success_rate:.1f}%")

    # Cache summary
    if cache_stats.get('global'):
        cache_hit_rate = cache_stats['global'].get('hit_rate', 0)
        api_saved = cache_stats['global'].get('api_calls_saved', 0)
        print(f"   Cache Hit Rate: {cache_hit_rate:.1f}%")
        print(f"   API Calls Saved: {format_number(api_saved)}")

    print("="*80)


def watch_metrics(interval=5):
    """Continuously display metrics"""
    print("📊 Starting metrics dashboard (Ctrl+C to stop)...")
    print(f"🔄 Refreshing every {interval} seconds...")

    try:
        while True:
            # Clear screen (works on both Windows and Unix)
            os.system('cls' if os.name == 'nt' else 'clear')

            show_metrics()

            print(f"\n⏳ Next refresh in {interval}s... (Press Ctrl+C to stop)")
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\n👋 Metrics dashboard stopped.")


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Display agent system metrics")
    parser.add_argument(
        '--watch',
        action='store_true',
        help='Continuously display metrics (refresh every 5s)'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=5,
        help='Refresh interval in seconds (default: 5)'
    )

    args = parser.parse_args()

    if args.watch:
        watch_metrics(interval=args.interval)
    else:
        show_metrics()


if __name__ == "__main__":
    main()
