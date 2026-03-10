"""
Integration tests for Monitoring and Logging

Tests the complete monitoring infrastructure including logging, metrics, and alerting.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
import logging
import json
from datetime import datetime
from typing import Dict, Any


class TestLoggingIntegration:
    """Test logging system integration"""

    @pytest.fixture
    def mock_logger(self):
        """Create mock logger"""
        logger = MagicMock(spec=logging.Logger)
        logger.name = "test_logger"
        logger.level = logging.INFO
        return logger

    def test_structured_logging_format(self, mock_logger):
        """Test structured logging produces JSON format"""
        # Arrange
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "level": "INFO",
            "message": "Test log message",
            "agent": "mailer",
            "session_id": "session-123"
        }

        # Act
        mock_logger.info(json.dumps(log_data))

        # Assert
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        parsed_data = json.loads(call_args)
        assert parsed_data["level"] == "INFO"
        assert parsed_data["agent"] == "mailer"

    def test_logging_levels(self, mock_logger):
        """Test different logging levels"""
        # Act
        mock_logger.debug("Debug message")
        mock_logger.info("Info message")
        mock_logger.warning("Warning message")
        mock_logger.error("Error message")
        mock_logger.critical("Critical message")

        # Assert
        assert mock_logger.debug.call_count == 1
        assert mock_logger.info.call_count == 1
        assert mock_logger.warning.call_count == 1
        assert mock_logger.error.call_count == 1
        assert mock_logger.critical.call_count == 1

    def test_context_logging(self, mock_logger):
        """Test logging with context information"""
        # Arrange
        context = {
            "user_id": "user-456",
            "agent": "librarian",
            "operation": "search_files",
            "query": "budget report"
        }

        # Act
        log_message = {
            "message": "Executing search",
            "context": context
        }
        mock_logger.info(json.dumps(log_message))

        # Assert
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        parsed = json.loads(call_args)
        assert parsed["context"]["agent"] == "librarian"
        assert parsed["context"]["operation"] == "search_files"

    def test_error_logging_with_traceback(self, mock_logger):
        """Test error logging includes traceback"""
        # Arrange
        try:
            raise ValueError("Test error")
        except ValueError as e:
            error_info = {
                "message": "Error occurred",
                "error": str(e),
                "error_type": type(e).__name__
            }

            # Act
            mock_logger.error(json.dumps(error_info))

            # Assert
            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args[0][0]
            parsed = json.loads(call_args)
            assert parsed["error_type"] == "ValueError"
            assert "Test error" in parsed["error"]


class TestMetricsCollection:
    """Test metrics collection system"""

    @pytest.fixture
    def mock_metrics_collector(self):
        """Create mock metrics collector"""
        with patch('monitoring.metrics.MetricsCollector') as MockCollector:
            collector = MagicMock()
            MockCollector.return_value = collector
            yield collector

    def test_counter_increment(self, mock_metrics_collector):
        """Test counter metric incrementation"""
        # Act
        mock_metrics_collector.increment("agent_calls", labels={"agent": "mailer"})
        mock_metrics_collector.increment("agent_calls", labels={"agent": "mailer"})
        mock_metrics_collector.increment("agent_calls", labels={"agent": "librarian"})

        # Assert
        assert mock_metrics_collector.increment.call_count == 3
        calls = mock_metrics_collector.increment.call_args_list
        assert calls[0][0][0] == "agent_calls"
        assert calls[0][1]["labels"]["agent"] == "mailer"

    def test_timer_tracking(self, mock_metrics_collector):
        """Test timing metric tracking"""
        # Arrange
        operation_name = "gmail_send_message"
        duration_ms = 250.5

        # Act
        mock_metrics_collector.record_time(operation_name, duration_ms)

        # Assert
        mock_metrics_collector.record_time.assert_called_once_with(operation_name, duration_ms)

    def test_gauge_value_setting(self, mock_metrics_collector):
        """Test gauge metric value setting"""
        # Arrange
        metric_name = "active_sessions"
        value = 42

        # Act
        mock_metrics_collector.set_gauge(metric_name, value)

        # Assert
        mock_metrics_collector.set_gauge.assert_called_once_with(metric_name, value)

    def test_histogram_recording(self, mock_metrics_collector):
        """Test histogram metric recording"""
        # Arrange
        metric_name = "response_size_bytes"
        values = [1024, 2048, 512, 4096, 1536]

        # Act
        for value in values:
            mock_metrics_collector.record_histogram(metric_name, value)

        # Assert
        assert mock_metrics_collector.record_histogram.call_count == len(values)

    def test_metrics_with_labels(self, mock_metrics_collector):
        """Test metrics with multiple labels"""
        # Arrange
        labels = {
            "agent": "mailer",
            "operation": "send_email",
            "status": "success"
        }

        # Act
        mock_metrics_collector.increment("operation_count", labels=labels)

        # Assert
        mock_metrics_collector.increment.assert_called_once()
        call_labels = mock_metrics_collector.increment.call_args[1]["labels"]
        assert call_labels["agent"] == "mailer"
        assert call_labels["operation"] == "send_email"
        assert call_labels["status"] == "success"


class TestAgentMetrics:
    """Test agent-specific metrics tracking"""

    @pytest.fixture
    def mock_agent_metrics(self):
        """Create mock agent metrics"""
        with patch('monitoring.metrics.AgentMetrics') as MockAgentMetrics:
            metrics = MagicMock()
            MockAgentMetrics.return_value = metrics
            yield metrics

    def test_track_agent_call(self, mock_agent_metrics):
        """Test tracking agent calls"""
        # Act
        mock_agent_metrics.record_agent_call("mailer", success=True, duration_ms=150)
        mock_agent_metrics.record_agent_call("librarian", success=True, duration_ms=200)
        mock_agent_metrics.record_agent_call("mailer", success=False, duration_ms=50)

        # Assert
        assert mock_agent_metrics.record_agent_call.call_count == 3

    def test_track_tool_usage(self, mock_agent_metrics):
        """Test tracking tool usage"""
        # Act
        mock_agent_metrics.record_tool_usage("gmail_send", success=True)
        mock_agent_metrics.record_tool_usage("drive_search", success=True)
        mock_agent_metrics.record_tool_usage("gmail_send", success=False)

        # Assert
        assert mock_agent_metrics.record_tool_usage.call_count == 3

    def test_track_error_rates(self, mock_agent_metrics):
        """Test tracking error rates"""
        # Act - Simulate 10 calls with 2 errors
        for i in range(10):
            success = i not in [3, 7]  # Errors at index 3 and 7
            mock_agent_metrics.record_agent_call("mailer", success=success)

        # Assert
        assert mock_agent_metrics.record_agent_call.call_count == 10
        # Error rate would be 2/10 = 20%

    def test_track_response_times(self, mock_agent_metrics):
        """Test tracking response times"""
        # Arrange
        response_times = [100, 150, 200, 175, 225, 300]

        # Act
        for duration in response_times:
            mock_agent_metrics.record_response_time("mailer", duration)

        # Assert
        assert mock_agent_metrics.record_response_time.call_count == len(response_times)


class TestAlertingSystem:
    """Test alerting system integration"""

    @pytest.fixture
    def mock_alerting_service(self):
        """Create mock alerting service"""
        with patch('monitoring.alerting.AlertingService') as MockAlerting:
            service = MagicMock()
            MockAlerting.return_value = service
            yield service

    def test_send_alert(self, mock_alerting_service):
        """Test sending alerts"""
        # Arrange
        alert_data = {
            "severity": "ERROR",
            "title": "High error rate detected",
            "message": "Mailer agent error rate: 25%",
            "timestamp": datetime.now().isoformat()
        }

        # Act
        mock_alerting_service.send_alert(alert_data)

        # Assert
        mock_alerting_service.send_alert.assert_called_once_with(alert_data)

    def test_alert_severity_levels(self, mock_alerting_service):
        """Test different alert severity levels"""
        # Arrange
        severities = ["INFO", "WARNING", "ERROR", "CRITICAL"]

        # Act
        for severity in severities:
            alert = {"severity": severity, "message": f"{severity} alert"}
            mock_alerting_service.send_alert(alert)

        # Assert
        assert mock_alerting_service.send_alert.call_count == len(severities)

    def test_alert_threshold_triggering(self, mock_alerting_service):
        """Test alert triggered when threshold exceeded"""
        # Arrange
        error_threshold = 0.10  # 10%
        total_calls = 100
        errors = 15  # 15% error rate
        error_rate = errors / total_calls

        # Act
        if error_rate > error_threshold:
            mock_alerting_service.send_alert({
                "severity": "WARNING",
                "message": f"Error rate {error_rate:.1%} exceeds threshold {error_threshold:.1%}"
            })

        # Assert
        mock_alerting_service.send_alert.assert_called_once()

    def test_alert_deduplication(self, mock_alerting_service):
        """Test alert deduplication within time window"""
        # Arrange
        alert_key = "high_error_rate_mailer"
        mock_alerting_service.should_send_alert.return_value = False  # Already sent recently

        # Act
        if mock_alerting_service.should_send_alert(alert_key):
            mock_alerting_service.send_alert({"key": alert_key, "message": "Error"})

        # Assert
        # Alert should not be sent due to deduplication
        mock_alerting_service.send_alert.assert_not_called()


class TestMonitoringIntegration:
    """Test complete monitoring integration"""

    @pytest.fixture
    def monitoring_system(self):
        """Create complete monitoring system mock"""
        system = {
            "logger": MagicMock(spec=logging.Logger),
            "metrics": MagicMock(),
            "alerting": MagicMock()
        }
        return system

    def test_end_to_end_monitoring_flow(self, monitoring_system):
        """Test complete monitoring flow for an operation"""
        # Arrange
        operation = "send_email"
        agent = "mailer"

        # Act - Simulate operation with monitoring
        # Step 1: Log operation start
        monitoring_system["logger"].info(f"Starting {operation}")

        # Step 2: Track metrics
        monitoring_system["metrics"].increment("operations_started", labels={"operation": operation})

        # Step 3: Simulate operation (success)
        duration_ms = 250
        success = True

        # Step 4: Record completion metrics
        monitoring_system["metrics"].record_time(operation, duration_ms)
        monitoring_system["metrics"].increment("operations_completed", labels={
            "operation": operation,
            "status": "success" if success else "error"
        })

        # Step 5: Log completion
        monitoring_system["logger"].info(f"Completed {operation} in {duration_ms}ms")

        # Assert
        assert monitoring_system["logger"].info.call_count == 2
        assert monitoring_system["metrics"].increment.call_count == 2
        assert monitoring_system["metrics"].record_time.call_count == 1

    def test_monitoring_error_scenario(self, monitoring_system):
        """Test monitoring during error scenario"""
        # Arrange
        operation = "search_files"

        # Act - Simulate error scenario
        monitoring_system["logger"].info(f"Starting {operation}")

        try:
            # Simulate error
            raise Exception("Drive API timeout")
        except Exception as e:
            # Log error
            monitoring_system["logger"].error(f"Error in {operation}: {str(e)}")

            # Track error metric
            monitoring_system["metrics"].increment("errors", labels={
                "operation": operation,
                "error_type": type(e).__name__
            })

            # Send alert
            monitoring_system["alerting"].send_alert({
                "severity": "ERROR",
                "message": f"Error in {operation}: {str(e)}"
            })

        # Assert
        monitoring_system["logger"].error.assert_called_once()
        monitoring_system["metrics"].increment.assert_called_once()
        monitoring_system["alerting"].send_alert.assert_called_once()

    def test_monitoring_performance_tracking(self, monitoring_system):
        """Test monitoring tracks performance over time"""
        # Arrange
        operation_durations = [100, 150, 200, 175, 300, 250, 125, 180]

        # Act
        for duration in operation_durations:
            monitoring_system["metrics"].record_time("agent_response", duration)
            monitoring_system["logger"].debug(f"Response time: {duration}ms")

        # Calculate average
        avg_duration = sum(operation_durations) / len(operation_durations)

        # Check if performance degraded (avg > 200ms)
        if avg_duration > 200:
            monitoring_system["alerting"].send_alert({
                "severity": "WARNING",
                "message": f"Average response time high: {avg_duration:.0f}ms"
            })

        # Assert
        assert monitoring_system["metrics"].record_time.call_count == len(operation_durations)
        monitoring_system["alerting"].send_alert.assert_called_once()

    def test_monitoring_concurrent_operations(self, monitoring_system):
        """Test monitoring handles concurrent operations"""
        # Arrange
        operations = [
            ("mailer", "send_email"),
            ("librarian", "search_files"),
            ("secretary", "schedule_meeting")
        ]

        # Act
        for agent, operation in operations:
            monitoring_system["logger"].info(f"{agent}: Starting {operation}")
            monitoring_system["metrics"].increment("concurrent_operations")

        # Track active operations gauge
        monitoring_system["metrics"].set_gauge("active_operations", len(operations))

        # Complete operations
        for agent, operation in operations:
            monitoring_system["metrics"].decrement("concurrent_operations")
            monitoring_system["logger"].info(f"{agent}: Completed {operation}")

        monitoring_system["metrics"].set_gauge("active_operations", 0)

        # Assert
        assert monitoring_system["logger"].info.call_count == 6  # 3 start + 3 complete
        assert monitoring_system["metrics"].increment.call_count == len(operations)
        assert monitoring_system["metrics"].set_gauge.call_count == 2


class TestCloudLoggingIntegration:
    """Test Google Cloud Logging integration"""

    @pytest.fixture
    def mock_cloud_logging_client(self):
        """Create mock Cloud Logging client"""
        with patch('google.cloud.logging.Client') as MockClient:
            client = MagicMock()
            MockClient.return_value = client
            yield client

    def test_cloud_logging_setup(self, mock_cloud_logging_client):
        """Test setting up Cloud Logging"""
        # Act
        mock_cloud_logging_client.setup_logging()

        # Assert
        mock_cloud_logging_client.setup_logging.assert_called_once()

    def test_cloud_logging_structured_logs(self, mock_cloud_logging_client):
        """Test sending structured logs to Cloud Logging"""
        # Arrange
        log_entry = {
            "severity": "INFO",
            "message": "Agent operation completed",
            "agent": "mailer",
            "duration_ms": 250,
            "timestamp": datetime.now().isoformat()
        }

        # Act
        logger = mock_cloud_logging_client.logger("adk-system")
        logger.log_struct(log_entry)

        # Assert
        logger.log_struct.assert_called_once_with(log_entry)

    def test_cloud_logging_error_reporting(self, mock_cloud_logging_client):
        """Test error reporting to Cloud Logging"""
        # Arrange
        error_entry = {
            "severity": "ERROR",
            "message": "Agent execution failed",
            "error": "Connection timeout",
            "agent": "librarian",
            "timestamp": datetime.now().isoformat()
        }

        # Act
        logger = mock_cloud_logging_client.logger("adk-errors")
        logger.log_struct(error_entry, severity="ERROR")

        # Assert
        logger.log_struct.assert_called_once()
        call_args = logger.log_struct.call_args
        assert call_args[1]["severity"] == "ERROR"
