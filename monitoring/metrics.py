"""
Metrics Collection

Collects and reports metrics for monitoring and alerting
Integrates with Google Cloud Logging for dashboard visualization
"""

import time
import logging
import json
import os
from typing import Dict, Any, Optional
from functools import wraps
from collections import defaultdict
from datetime import datetime

# Import Google Cloud Logging
try:
    import google.cloud.logging
    from google.cloud.logging.handlers import CloudLoggingHandler
    GCP_LOGGING_AVAILABLE = True
except ImportError:
    GCP_LOGGING_AVAILABLE = False

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects application metrics and exports to Cloud Logging"""

    def __init__(self):
        self.metrics = defaultdict(int)
        self.timings = defaultdict(list)
        self.errors = defaultdict(int)
        self.cloud_logger = None
        
        # Initialize Cloud Logging if available and configured
        if GCP_LOGGING_AVAILABLE and os.getenv("USE_CLOUD_LOGGING", "false").lower() == "true":
            try:
                client = google.cloud.logging.Client()
                self.cloud_logger = client.logger("adk-agent-system")
                logger.info("Cloud Logging initialized for metrics")
            except Exception as e:
                logger.warning(f"Failed to initialize Cloud Logging: {e}")

    def _log_to_cloud(self, event_type: str, payload: Dict[str, Any]):
        """Log structured data to Google Cloud Logging"""
        if self.cloud_logger:
            try:
                # Add timestamp and event type
                payload["event_type"] = event_type
                payload["timestamp"] = datetime.utcnow().isoformat()
                
                # Log as structured JSON
                self.cloud_logger.log_struct(payload)
            except Exception as e:
                logger.debug(f"Failed to send log to Cloud: {e}")

    def increment(self, metric_name: str, value: int = 1, labels: Optional[Dict] = None):
        """Increment a counter metric"""
        key = self._make_key(metric_name, labels)
        self.metrics[key] += value
        logger.debug(f"Metric incremented: {key} += {value}")
        
        # Export to Cloud Logging
        payload = {
            "metric_name": metric_name,
            "value": value,
            "metric_type": "counter"
        }
        if labels:
            payload.update(labels)
            
        self._log_to_cloud(f"{metric_name}_event", payload)

    def record_timing(self, metric_name: str, duration: float, labels: Optional[Dict] = None):
        """Record a timing metric"""
        key = self._make_key(metric_name, labels)
        self.timings[key].append(duration)
        logger.debug(f"Timing recorded: {key} = {duration:.3f}s")
        
        # Export to Cloud Logging
        payload = {
            "metric_name": metric_name,
            "duration_ms": duration * 1000,  # Convert to ms
            "metric_type": "timing"
        }
        if labels:
            payload.update(labels)
            
        self._log_to_cloud(f"{metric_name}_event", payload)

    def record_error(self, error_type: str, labels: Optional[Dict] = None):
        """Record an error"""
        key = self._make_key(error_type, labels)
        self.errors[key] += 1
        logger.debug(f"Error recorded: {key}")
        
        # Export to Cloud Logging
        payload = {
            "error_type": error_type,
            "metric_type": "error"
        }
        if labels:
            payload.update(labels)
            
        self._log_to_cloud("agent_request_error", payload)

    def get_metrics(self) -> Dict[str, Any]:
        """Get all collected metrics"""
        return {
            "counters": dict(self.metrics),
            "timings": {
                k: {
                    "count": len(v),
                    "avg": sum(v) / len(v) if v else 0,
                    "min": min(v) if v else 0,
                    "max": max(v) if v else 0
                }
                for k, v in self.timings.items()
            },
            "errors": dict(self.errors),
            "timestamp": datetime.utcnow().isoformat()
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary (alias for get_metrics for backwards compatibility)"""
        return self.get_metrics()

    def reset(self):
        """Reset all metrics"""
        self.metrics.clear()
        self.timings.clear()
        self.errors.clear()

    def _make_key(self, name: str, labels: Optional[Dict] = None) -> str:
        """Create metric key with labels"""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}[{label_str}]"


# Global metrics collector
_metrics_collector = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """Get global metrics collector"""
    return _metrics_collector


def track_time(metric_name: str):
    """Decorator to track execution time"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                _metrics_collector.record_timing(
                    metric_name,
                    duration,
                    labels={"function": func.__name__}
                )
        return wrapper
    return decorator


def track_errors(error_type: str = "error"):
    """Decorator to track errors"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                _metrics_collector.record_error(
                    error_type,
                    labels={
                        "function": func.__name__,
                        "exception": type(e).__name__
                    }
                )
                raise
        return wrapper
    return decorator


# Example usage in agents
class AgentMetrics:
    """Metrics specific to agents"""

    @staticmethod
    def record_agent_call(agent_name: str, success: bool = True):
        """Record agent invocation"""
        event_type = "agent_request_success" if success else "agent_request_error"
        
        # For success, we use increment but specify the event type in _log_to_cloud
        # However, increment uses {metric_name}_event. 
        # So we need to be careful to match the dashboard filters:
        # jsonPayload.event_type="agent_request_success"
        
        if success:
            _metrics_collector.cloud_logger.log_struct({
                "event_type": "agent_request_success",
                "agent_name": agent_name,
                "timestamp": datetime.utcnow().isoformat()
            }) if _metrics_collector.cloud_logger else None
            
            _metrics_collector.increment(
                "agent_calls",
                labels={"agent": agent_name, "success": "True"}
            )
        else:
            _metrics_collector.cloud_logger.log_struct({
                "event_type": "agent_request_error",
                "agent_name": agent_name,
                "timestamp": datetime.utcnow().isoformat()
            }) if _metrics_collector.cloud_logger else None
            
            _metrics_collector.increment(
                "agent_calls",
                labels={"agent": agent_name, "success": "False"}
            )

    @staticmethod
    def record_tool_call(agent_name: str, tool_name: str, success: bool = True):
        """Record tool invocation"""
        if success:
            _metrics_collector.cloud_logger.log_struct({
                "event_type": "tool_execution_success",
                "agent_name": agent_name,
                "tool_name": tool_name,
                "timestamp": datetime.utcnow().isoformat()
            }) if _metrics_collector.cloud_logger else None

        _metrics_collector.increment(
            "tool_calls",
            labels={
                "agent": agent_name,
                "tool": tool_name,
                "success": str(success)
            }
        )

    @staticmethod
    def record_routing(from_agent: str, to_agent: str):
        """Record agent routing"""
        _metrics_collector.increment(
            "agent_routing",
            labels={"from": from_agent, "to": to_agent}
        )
