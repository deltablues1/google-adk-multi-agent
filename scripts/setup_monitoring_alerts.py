"""
Setup Google Cloud Monitoring Alerts
=====================================

Creates essential alerts for ADK Agent System:
1. High Error Rate Alert (> 5 errors/minute)
2. High Latency Alert (> 30 seconds)

Usage:
    python scripts/setup_monitoring_alerts.py
"""

import os
import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()


def create_error_rate_alert(client, project_name, project_id):
    """Create alert for high error rate"""
    print("\n📢 Creating Error Rate Alert...")

    alert_policy = {
        "display_name": "ADK Agent System - High Error Rate",
        "documentation": {
            "content": (
                "Agent system is experiencing high error rate (> 5 errors/minute).\n\n"
                "**Action Required:**\n"
                "1. Check Cloud Logging for error details\n"
                "2. Review recent deployments\n"
                "3. Check Vertex AI service status\n\n"
                f"View logs: https://console.cloud.google.com/logs?project={project_id}"
            ),
            "mime_type": "text/markdown"
        },
        "conditions": [{
            "display_name": "Error rate > 5/min",
            "condition_threshold": {
                "filter": (
                    'resource.type="global" '
                    'AND logName=~".*adk-agent-system.*" '
                    'AND jsonPayload.event_type="agent_request_error"'
                ),
                "aggregations": [{
                    "alignment_period": {"seconds": 60},
                    "per_series_aligner": "ALIGN_RATE",
                    "cross_series_reducer": "REDUCE_SUM"
                }],
                "comparison": "COMPARISON_GT",
                "threshold_value": 5.0,
                "duration": {"seconds": 120}  # Alert if condition lasts 2 minutes
            }
        }],
        "combiner": "OR",
        "enabled": True,
        "notification_channels": [],  # Add notification channels here
        "alert_strategy": {
            "auto_close": {"seconds": 1800}  # Auto-close after 30 minutes
        }
    }

    try:
        from google.cloud import monitoring_v3

        response = client.create_alert_policy(
            name=project_name,
            alert_policy=alert_policy
        )

        print(f"✅ Error Rate Alert created: {response.name}")
        return response

    except Exception as e:
        print(f"❌ Failed to create Error Rate Alert: {e}")
        return None


def create_latency_alert(client, project_name, project_id):
    """Create alert for high latency"""
    print("\n📢 Creating Latency Alert...")

    alert_policy = {
        "display_name": "ADK Agent System - High Latency",
        "documentation": {
            "content": (
                "Agent requests are taking longer than 30 seconds.\n\n"
                "**Action Required:**\n"
                "1. Check Vertex AI latency metrics\n"
                "2. Review tool execution times\n"
                "3. Check for quota limits\n\n"
                f"View metrics: https://console.cloud.google.com/monitoring/metrics-explorer?project={project_id}"
            ),
            "mime_type": "text/markdown"
        },
        "conditions": [{
            "display_name": "Average latency > 30s",
            "condition_threshold": {
                "filter": (
                    'resource.type="global" '
                    'AND logName=~".*adk-agent-system.*" '
                    'AND jsonPayload.event_type="agent_request_success"'
                ),
                "aggregations": [{
                    "alignment_period": {"seconds": 60},
                    "per_series_aligner": "ALIGN_MEAN",
                    "cross_series_reducer": "REDUCE_MEAN"
                }],
                "comparison": "COMPARISON_GT",
                "threshold_value": 30.0,
                "duration": {"seconds": 300}  # Alert if condition lasts 5 minutes
            }
        }],
        "combiner": "OR",
        "enabled": True,
        "notification_channels": [],  # Add notification channels here
        "alert_strategy": {
            "auto_close": {"seconds": 1800}  # Auto-close after 30 minutes
        }
    }

    try:
        from google.cloud import monitoring_v3

        response = client.create_alert_policy(
            name=project_name,
            alert_policy=alert_policy
        )

        print(f"✅ Latency Alert created: {response.name}")
        return response

    except Exception as e:
        print(f"❌ Failed to create Latency Alert: {e}")
        return None


def list_notification_channels(project_id):
    """List available notification channels"""
    print("\n📧 Checking notification channels...")

    try:
        from google.cloud import monitoring_v3

        client = monitoring_v3.NotificationChannelServiceClient()
        project_name = f"projects/{project_id}"

        channels = list(client.list_notification_channels(name=project_name))

        if channels:
            print(f"✅ Found {len(channels)} notification channel(s):")
            for channel in channels:
                print(f"   • {channel.display_name} ({channel.type_})")
        else:
            print("ℹ️  No notification channels configured yet")
            print("\n💡 To add notification channels:")
            print(f"   https://console.cloud.google.com/monitoring/alerting/notifications?project={project_id}")
            print("\n   Available channel types:")
            print("   • Email")
            print("   • SMS")
            print("   • Slack")
            print("   • PagerDuty")
            print("   • Webhooks")

        return channels

    except Exception as e:
        print(f"⚠️  Could not list notification channels: {e}")
        return []


def setup_alerts():
    """Setup all monitoring alerts"""
    from google.cloud import monitoring_v3

    project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
    if not project_id:
        print("❌ GOOGLE_CLOUD_PROJECT not set in .env file!")
        return 1

    print(f"\n📊 Setting up monitoring alerts for project: {project_id}\n")

    try:
        client = monitoring_v3.AlertPolicyServiceClient()
        project_name = f"projects/{project_id}"

        # List notification channels first
        channels = list_notification_channels(project_id)

        # Create alerts
        error_alert = create_error_rate_alert(client, project_name, project_id)
        latency_alert = create_latency_alert(client, project_name, project_id)

        # Summary
        print("\n" + "="*80)
        print("  ✅ ALERT SETUP COMPLETE")
        print("="*80)

        success_count = sum([1 for a in [error_alert, latency_alert] if a is not None])
        print(f"\n✅ Created {success_count}/2 alerts")

        if success_count > 0:
            print(f"\n🔗 View alerts at:")
            print(f"   https://console.cloud.google.com/monitoring/alerting/policies?project={project_id}")

        if not channels:
            print(f"\n⚠️  No notification channels configured!")
            print(f"   Alerts are active but won't send notifications.")
            print(f"\n💡 To add notifications:")
            print(f"   1. Go to: https://console.cloud.google.com/monitoring/alerting/notifications?project={project_id}")
            print(f"   2. Create a notification channel (email/SMS/Slack)")
            print(f"   3. Edit alerts to add the channel")

        print("\n📋 What happens when alerts trigger:")
        print("   • Alert appears in Cloud Console")
        if channels:
            print("   • Notifications sent via configured channels")
        print("   • Incident is tracked until resolved")
        print("   • Auto-closes after 30 minutes if condition clears")

        return 0

    except Exception as e:
        print(f"\n❌ Error setting up alerts: {e}")
        return 1


def main():
    """Main execution"""
    print("\n" + "="*80)
    print("  📢 Google Cloud Monitoring Alerts Setup")
    print("="*80)

    try:
        from google.cloud import monitoring_v3
        print("✅ google-cloud-monitoring package found")
    except ImportError:
        print("\n❌ google-cloud-monitoring not installed!")
        print("   Install with: pip install google-cloud-monitoring")
        return 1

    return setup_alerts()


if __name__ == "__main__":
    sys.exit(main())
