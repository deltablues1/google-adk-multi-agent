"""
Google Cloud Monitoring & Logging Explorer
===========================================

Ovaj script provjerava što već postoji u Google Cloud-u za monitoring:
- Cloud Logging (logs)
- Cloud Monitoring (metrics)
- Vertex AI usage
- Error Reporting

Usage:
    python scripts/check_cloud_monitoring.py
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()


def print_section(title: str):
    """Print formatted section header"""
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")


def check_cloud_logging():
    """Check Cloud Logging setup and recent logs"""
    print_section("📋 CLOUD LOGGING")

    project_id = os.getenv('GOOGLE_CLOUD_PROJECT')

    try:
        from google.cloud import logging

        # Initialize client
        client = logging.Client(project=project_id)

        print(f"✅ Cloud Logging Client initialized")
        print(f"   Project: {project_id}")

        # Try to list recent logs
        print(f"\n🔍 Checking recent logs...")

        # Get logs from last 24 hours
        filter_str = f'timestamp >= "{(datetime.utcnow() - timedelta(days=1)).isoformat()}Z"'

        entries = list(client.list_entries(
            filter_=filter_str,
            page_size=10,
            order_by=logging.DESCENDING
        ))

        if entries:
            print(f"✅ Found {len(entries)} recent log entries")
            print(f"\n📝 Sample recent logs:")
            for i, entry in enumerate(entries[:3], 1):
                print(f"\n   [{i}] {entry.timestamp}")
                print(f"       Severity: {entry.severity}")
                print(f"       Log: {entry.log_name}")
                if hasattr(entry, 'payload'):
                    payload_str = str(entry.payload)[:100]
                    print(f"       Payload: {payload_str}...")
        else:
            print(f"⚠️  No logs found in last 24 hours")
            print(f"   This is normal if you haven't run the system recently")

        # Print Cloud Console link
        print(f"\n🔗 Cloud Logging Explorer:")
        print(f"   https://console.cloud.google.com/logs/query?project={project_id}")

        return True

    except ImportError:
        print(f"❌ google-cloud-logging package not installed")
        print(f"   Install: pip install google-cloud-logging")
        return False
    except Exception as e:
        print(f"❌ Error accessing Cloud Logging: {e}")
        return False


def check_cloud_monitoring():
    """Check Cloud Monitoring metrics"""
    print_section("📊 CLOUD MONITORING")

    project_id = os.getenv('GOOGLE_CLOUD_PROJECT')

    try:
        from google.cloud import monitoring_v3

        # Initialize client
        client = monitoring_v3.MetricServiceClient()
        project_name = f"projects/{project_id}"

        print(f"✅ Cloud Monitoring Client initialized")
        print(f"   Project: {project_id}")

        # List available metric descriptors
        print(f"\n🔍 Checking available metrics...")

        # Filter for Vertex AI metrics
        filter_str = 'metric.type = starts_with("aiplatform.googleapis.com/")'

        descriptors = client.list_metric_descriptors(
            name=project_name,
            filter=filter_str
        )

        vertex_metrics = list(descriptors)

        if vertex_metrics:
            print(f"✅ Found {len(vertex_metrics)} Vertex AI metrics available")
            print(f"\n📈 Sample Vertex AI metrics:")
            for i, descriptor in enumerate(vertex_metrics[:5], 1):
                print(f"   [{i}] {descriptor.type}")
                print(f"       Description: {descriptor.description}")
        else:
            print(f"⚠️  No Vertex AI metrics found yet")
            print(f"   Metrics appear after first API calls to Vertex AI")

        # Check for custom metrics
        print(f"\n🔍 Checking custom metrics...")
        custom_filter = 'metric.type = starts_with("custom.googleapis.com/")'
        custom_descriptors = list(client.list_metric_descriptors(
            name=project_name,
            filter=custom_filter
        ))

        if custom_descriptors:
            print(f"✅ Found {len(custom_descriptors)} custom metrics")
        else:
            print(f"ℹ️  No custom metrics yet (we can create these!)")

        # Print Cloud Console links
        print(f"\n🔗 Cloud Monitoring:")
        print(f"   Metrics Explorer: https://console.cloud.google.com/monitoring/metrics-explorer?project={project_id}")
        print(f"   Dashboards: https://console.cloud.google.com/monitoring/dashboards?project={project_id}")

        return True

    except ImportError:
        print(f"❌ google-cloud-monitoring package not installed")
        print(f"   Install: pip install google-cloud-monitoring")
        return False
    except Exception as e:
        print(f"❌ Error accessing Cloud Monitoring: {e}")
        print(f"   Error details: {type(e).__name__}")
        return False


def check_vertex_ai_usage():
    """Check Vertex AI usage and quota"""
    print_section("🤖 VERTEX AI USAGE")

    project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
    location = os.getenv('VERTEX_AI_LOCATION', 'us-central1')

    print(f"📍 Project: {project_id}")
    print(f"📍 Location: {location}")

    # Print useful links
    print(f"\n🔗 Vertex AI Console:")
    print(f"   Dashboard: https://console.cloud.google.com/vertex-ai?project={project_id}")
    print(f"   Generative AI: https://console.cloud.google.com/vertex-ai/generative?project={project_id}")
    print(f"   Quotas: https://console.cloud.google.com/iam-admin/quotas?project={project_id}")

    # Try to get usage data
    try:
        from google.cloud import monitoring_v3

        client = monitoring_v3.MetricServiceClient()
        project_name = f"projects/{project_id}"

        # Query for Vertex AI API calls in last 7 days
        interval = monitoring_v3.TimeInterval({
            "end_time": {"seconds": int(datetime.utcnow().timestamp())},
            "start_time": {"seconds": int((datetime.utcnow() - timedelta(days=7)).timestamp())}
        })

        # Check prediction requests
        results = client.list_time_series(
            request={
                "name": project_name,
                "filter": 'metric.type = "aiplatform.googleapis.com/prediction/online/response_count"',
                "interval": interval,
                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL
            }
        )

        time_series = list(results)
        if time_series:
            print(f"\n✅ Found Vertex AI usage data (last 7 days)")
            total_requests = sum(
                sum(point.value.int64_value or 0 for point in series.points)
                for series in time_series
            )
            print(f"   Total API requests: {total_requests}")
        else:
            print(f"\nℹ️  No Vertex AI usage data found in last 7 days")
            print(f"   Data appears after making Vertex AI API calls")

    except Exception as e:
        print(f"\nℹ️  Could not fetch usage data: {type(e).__name__}")
        print(f"   This is normal - check the console links above")


def check_error_reporting():
    """Check Error Reporting"""
    print_section("🐛 ERROR REPORTING")

    project_id = os.getenv('GOOGLE_CLOUD_PROJECT')

    print(f"🔗 Error Reporting Console:")
    print(f"   https://console.cloud.google.com/errors?project={project_id}")

    try:
        from google.cloud import errorreporting

        client = errorreporting.Client(project=project_id)
        print(f"\n✅ Error Reporting Client initialized")
        print(f"   Errors are automatically captured from Cloud Logging")

    except ImportError:
        print(f"\nℹ️  google-cloud-error-reporting not installed (optional)")
        print(f"   Error Reporting still works via Cloud Logging")
    except Exception as e:
        print(f"\nℹ️  Error Reporting check: {type(e).__name__}")


def check_billing():
    """Check billing and cost information"""
    print_section("💰 BILLING & COSTS")

    project_id = os.getenv('GOOGLE_CLOUD_PROJECT')

    print(f"🔗 Billing & Cost Reports:")
    print(f"   Overview: https://console.cloud.google.com/billing?project={project_id}")
    print(f"   Reports: https://console.cloud.google.com/billing/reports?project={project_id}")
    print(f"   Budgets & Alerts: https://console.cloud.google.com/billing/budgets?project={project_id}")

    print(f"\nℹ️  Billing data updates daily")
    print(f"   Check the console for current costs")


def print_summary():
    """Print summary and next steps"""
    print_section("🎯 SUMMARY & NEXT STEPS")

    project_id = os.getenv('GOOGLE_CLOUD_PROJECT')

    print("✅ WHAT'S ALREADY AVAILABLE:")
    print("   • Cloud Logging - Automatic log collection")
    print("   • Cloud Monitoring - Metrics from all GCP services")
    print("   • Error Reporting - Auto-groups errors from logs")
    print("   • Vertex AI metrics - API calls, latency, tokens")
    print("   • Billing data - Cost tracking and reports")

    print("\n🚀 WHAT WE CAN ADD:")
    print("   • Custom metrics (agent success rate, workflow completion)")
    print("   • Structured logging (JSON format with context)")
    print("   • Custom dashboards (specific to your ADK system)")
    print("   • Alerts (email/SMS when issues occur)")
    print("   • Trace correlation (follow requests across agents)")

    print("\n📋 RECOMMENDED ACTIONS:")
    print("   1. Open Cloud Console links above")
    print("   2. Check existing logs and metrics")
    print("   3. Set up billing alerts (if not done)")
    print("   4. Decide which custom metrics you want")
    print("   5. Create monitoring dashboard")

    print(f"\n🔗 QUICK ACCESS:")
    print(f"   Console: https://console.cloud.google.com/?project={project_id}")
    print(f"   Logs: https://console.cloud.google.com/logs?project={project_id}")
    print(f"   Metrics: https://console.cloud.google.com/monitoring?project={project_id}")


def main():
    """Main execution"""
    print("\n" + "="*80)
    print("  🔍 Google Cloud Monitoring Explorer")
    print("  Checking what already exists in your GCP project...")
    print("="*80)

    project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
    if not project_id:
        print("\n❌ GOOGLE_CLOUD_PROJECT not set in .env file!")
        return 1

    print(f"\n📍 Project ID: {project_id}")
    print(f"📍 Location: {os.getenv('VERTEX_AI_LOCATION', 'us-central1')}")

    # Run checks
    logging_ok = check_cloud_logging()
    monitoring_ok = check_cloud_monitoring()
    check_vertex_ai_usage()
    check_error_reporting()
    check_billing()

    # Print summary
    print_summary()

    # Final status
    print_section("✅ EXPLORATION COMPLETE")

    if logging_ok and monitoring_ok:
        print("All checks passed! Your GCP project is ready for enhanced monitoring.")
    else:
        print("Some packages missing - install them to enable full monitoring:")
        print("  pip install google-cloud-logging google-cloud-monitoring")

    print("\n💡 TIP: Open the Console links above to explore visually!")
    print("\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
