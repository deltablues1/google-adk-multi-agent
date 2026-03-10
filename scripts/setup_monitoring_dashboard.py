"""
Setup Google Cloud Monitoring Dashboard
========================================

Creates a custom dashboard for ADK Agent System monitoring with:
- Agent success rates
- Request latency
- Tool execution metrics
- Error rates
- API call volumes

Usage:
    python scripts/setup_monitoring_dashboard.py
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


def create_dashboard():
    """Create monitoring dashboard in Google Cloud"""
    from google.cloud import monitoring_dashboard_v1
    import json

    project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
    if not project_id:
        print("❌ GOOGLE_CLOUD_PROJECT not set in .env file!")
        return 1

    print(f"\n📊 Creating monitoring dashboard for project: {project_id}\n")

    client = monitoring_dashboard_v1.DashboardsServiceClient()
    parent = f"projects/{project_id}"

    # Dashboard configuration
    dashboard_config = {
        "displayName": "ADK Agent System - Monitoring Dashboard",
        "mosaicLayout": {
            "columns": 12,
            "tiles": [
                # Tile 1: Agent Success Rate
                {
                    "width": 6,
                    "height": 4,
                    "widget": {
                        "title": "Agent Success Rate (%)",
                        "xyChart": {
                            "dataSets": [{
                                "timeSeriesQuery": {
                                    "timeSeriesFilter": {
                                        "filter": 'resource.type="global" AND logName=~".*adk-agent-system.*" AND jsonPayload.event_type="agent_request_success"',
                                        "aggregation": {
                                            "alignmentPeriod": "60s",
                                            "perSeriesAligner": "ALIGN_RATE",
                                            "crossSeriesReducer": "REDUCE_SUM",
                                            "groupByFields": ["jsonPayload.agent_name"]
                                        }
                                    }
                                },
                                "plotType": "LINE",
                                "targetAxis": "Y1"
                            }],
                            "yAxis": {
                                "label": "Success Rate",
                                "scale": "LINEAR"
                            }
                        }
                    }
                },
                # Tile 2: Request Latency
                {
                    "xPos": 6,
                    "width": 6,
                    "height": 4,
                    "widget": {
                        "title": "Agent Request Latency (seconds)",
                        "xyChart": {
                            "dataSets": [{
                                "timeSeriesQuery": {
                                    "timeSeriesFilter": {
                                        "filter": 'resource.type="global" AND logName=~".*adk-agent-system.*" AND jsonPayload.event_type="agent_request_success"',
                                        "aggregation": {
                                            "alignmentPeriod": "60s",
                                            "perSeriesAligner": "ALIGN_MEAN",
                                            "crossSeriesReducer": "REDUCE_MEAN",
                                            "groupByFields": ["jsonPayload.agent_name"]
                                        }
                                    }
                                },
                                "plotType": "LINE",
                                "targetAxis": "Y1"
                            }],
                            "yAxis": {
                                "label": "Latency (s)",
                                "scale": "LINEAR"
                            }
                        }
                    }
                },
                # Tile 3: Error Rate
                {
                    "yPos": 4,
                    "width": 6,
                    "height": 4,
                    "widget": {
                        "title": "Error Rate (errors/min)",
                        "xyChart": {
                            "dataSets": [{
                                "timeSeriesQuery": {
                                    "timeSeriesFilter": {
                                        "filter": 'resource.type="global" AND logName=~".*adk-agent-system.*" AND jsonPayload.event_type="agent_request_error"',
                                        "aggregation": {
                                            "alignmentPeriod": "60s",
                                            "perSeriesAligner": "ALIGN_RATE",
                                            "crossSeriesReducer": "REDUCE_SUM",
                                            "groupByFields": ["jsonPayload.agent_name"]
                                        }
                                    }
                                },
                                "plotType": "LINE",
                                "targetAxis": "Y1"
                            }],
                            "yAxis": {
                                "label": "Errors/min",
                                "scale": "LINEAR"
                            }
                        }
                    }
                },
                # Tile 4: Tool Execution Count
                {
                    "xPos": 6,
                    "yPos": 4,
                    "width": 6,
                    "height": 4,
                    "widget": {
                        "title": "Tool Executions (per minute)",
                        "xyChart": {
                            "dataSets": [{
                                "timeSeriesQuery": {
                                    "timeSeriesFilter": {
                                        "filter": 'resource.type="global" AND logName=~".*adk-agent-system.*" AND jsonPayload.event_type="tool_execution_success"',
                                        "aggregation": {
                                            "alignmentPeriod": "60s",
                                            "perSeriesAligner": "ALIGN_RATE",
                                            "crossSeriesReducer": "REDUCE_SUM",
                                            "groupByFields": ["jsonPayload.tool_name"]
                                        }
                                    }
                                },
                                "plotType": "STACKED_AREA",
                                "targetAxis": "Y1"
                            }],
                            "yAxis": {
                                "label": "Executions/min",
                                "scale": "LINEAR"
                            }
                        }
                    }
                },
                # Tile 5: Vertex AI API Calls
                {
                    "yPos": 8,
                    "width": 12,
                    "height": 4,
                    "widget": {
                        "title": "Vertex AI API Call Volume",
                        "xyChart": {
                            "dataSets": [{
                                "timeSeriesQuery": {
                                    "timeSeriesFilter": {
                                        "filter": 'metric.type="aiplatform.googleapis.com/prediction/online/response_count"',
                                        "aggregation": {
                                            "alignmentPeriod": "60s",
                                            "perSeriesAligner": "ALIGN_RATE",
                                            "crossSeriesReducer": "REDUCE_SUM"
                                        }
                                    }
                                },
                                "plotType": "LINE",
                                "targetAxis": "Y1"
                            }],
                            "yAxis": {
                                "label": "Calls/min",
                                "scale": "LINEAR"
                            }
                        }
                    }
                }
            ]
        }
    }

    try:
        dashboard = monitoring_dashboard_v1.Dashboard(
            json.loads(json.dumps(dashboard_config))
        )

        response = client.create_dashboard(
            parent=parent,
            dashboard=dashboard
        )

        print("✅ Dashboard created successfully!")
        print(f"\n📊 Dashboard Name: {response.name}")
        print(f"\n🔗 View dashboard at:")
        print(f"   https://console.cloud.google.com/monitoring/dashboards/custom/{response.name.split('/')[-1]}?project={project_id}")
        print(f"\n💡 TIP: You can customize this dashboard in the Cloud Console")

        return 0

    except Exception as e:
        print(f"❌ Error creating dashboard: {e}")
        print(f"\n💡 You can also create dashboards manually in Cloud Console:")
        print(f"   https://console.cloud.google.com/monitoring/dashboards?project={project_id}")
        return 1


def main():
    """Main execution"""
    print("\n" + "="*80)
    print("  📊 Google Cloud Monitoring Dashboard Setup")
    print("="*80)

    try:
        from google.cloud import monitoring_dashboard_v1
        print("✅ google-cloud-monitoring package found")
    except ImportError:
        print("\n❌ google-cloud-monitoring not installed!")
        print("   Install with: pip install google-cloud-monitoring")
        return 1

    return create_dashboard()


if __name__ == "__main__":
    sys.exit(main())
