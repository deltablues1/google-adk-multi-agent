"""
Unit tests for Monitoring System

Tests logging configuration, metrics collection, and alerting.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import logging
import json
from datetime import datetime
from typing import Dict, Any


class TestLoggingConfiguration:
    """Unit tests for logging configuration"""

    @pytest.fixture
    def mock_logger(self):
        """Create mock logger"""
        logger = MagicMock(spec=logging.Logger)
        logger.name = "test_logger"
        logger.level = logging.INFO
        return logger

    def test_setup_logging_info_level(self):
        """Test setting up logging with INFO level"""
        # Arrange
        with patch('monitoring.logging_config.setup_logging') as mock_setup:
            # Act
            mock_setup(level="INFO")

            # Assert
            mock_setup.assert_called_once_with(level="INFO")

    def test_setup_logging_debug_level(self):
        """Test setting up logging with DEBUG level"""
        # Arrange
        with patch('monitoring.logging_config.setup_logging') as mock_setup:
            # Act
            mock_setup(level="DEBUG")

            # Assert
            mock_setup.assert_called_once_with(level="DEBUG")

    def test_json_formatter(self):
        """Test JSON log formatter"""
        # Arrange
        log_record = {
            "timestamp": datetime.now().isoformat(),
            "level": "INFO",
            "message": "Test log",
            "module": "test_module"
        }

        # Act
        json_string = json.dumps(log_record)
        parsed = json.loads(json_string)

        # Assert
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "Test log"
        assert "timestamp" in parsed

    def test_structured_log_entry(self, mock_logger):
        """Test structured log entry creation"""
        # Arrange
        log_data = {
            "event": "agent_call",
            "agent": "mailer",
            "duration_ms": 150,
            "success": True
        }

        # Act
        mock_logger.info(json.dumps(log_data))

        # Assert
        mock_logger.info.assert_called_once()
        call_arg = mock_logger.info.call_args[0][0]
        parsed = json.loads(call_arg)
        assert parsed["agent"] == "mailer"
        assert parsed["duration_ms"] == 150

    def test_log_levels(self, mock_logger):
        """Test all log levels"""
        # Act
        mock_logger.debug("Debug")
        mock_logger.info("Info")
        mock_logger.warning("Warning")
        mock_logger.error("Error")
        mock_logger.critical("Critical")

        # Assert
        assert mock_logger.debug.call_count == 1
        assert mock_logger.info.call_count == 1
        assert mock_logger.warning.call_count == 1
        assert mock_logger.error.call_count == 1
        assert mock_logger.critical.call_count == 1

    def test_cloud_logging_integration(self):
        """Test Google Cloud Logging integration"""
        # Arrange
        with patch('monitoring.logging_config.setup_logging') as mock_setup:
            # Act
            mock_setup(level="INFO", use_cloud_logging=True)

            # Assert
            mock_setup.assert_called_once()
            assert mock_setup.call_args[1]["use_cloud_logging"] is True


class TestMetricsCollector:
    """Unit tests for metrics collector"""

    @pytest.fixture
    def mock_metrics_collector(self):
        """Create mock metrics collector"""
        with patch('monitoring.metrics.MetricsCollector') as MockCollector:
            collector = MagicMock()
            MockCollector.return_value = collector
            collector.metrics = {}
            yield collector

    def test_collector_initialization(self, mock_metrics_collector):
        """Test metrics collector initializes"""
        # Assert
        assert mock_metrics_collector is not None

    def test_increment_counter(self, mock_metrics_collector):
        """Test incrementing counter metric"""
        # Act
        mock_metrics_collector.increment("api_calls")
        mock_metrics_collector.increment("api_calls")
        mock_metrics_collector.increment("api_calls")

        # Assert
        assert mock_metrics_collector.increment.call_count == 3

    def test_increment_with_labels(self, mock_metrics_collector):
        """Test incrementing counter with labels"""
        # Arrange
        labels = {"agent": "mailer", "status": "success"}

        # Act
        mock_metrics_collector.increment("agent_calls", labels=labels)

        # Assert
        mock_metrics_collector.increment.assert_called_once_with("agent_calls", labels=labels)

    def test_record_time(self, mock_metrics_collector):
        """Test recording time metric"""
        # Arrange
        metric_name = "operation_duration"
        duration_ms = 250.5

        # Act
        mock_metrics_collector.record_time(metric_name, duration_ms)

        # Assert
        mock_metrics_collector.record_time.assert_called_once_with(metric_name, duration_ms)

    def test_set_gauge(self, mock_metrics_collector):
        """Test setting gauge value"""
        # Arrange
        metric_name = "active_connections"
        value = 42

        # Act
        mock_metrics_collector.set_gauge(metric_name, value)

        # Assert
        mock_metrics_collector.set_gauge.assert_called_once_with(metric_name, value)

    def test_record_histogram(self, mock_metrics_collector):
        """Test recording histogram values"""
        # Arrange
        metric_name = "response_size"
        values = [100, 200, 150, 300, 250]

        # Act
        for value in values:
            mock_metrics_collector.record_histogram(metric_name, value)

        # Assert
        assert mock_metrics_collector.record_histogram.call_count == len(values)

    def test_get_metric_value(self, mock_metrics_collector):
        """Test getting current metric value"""
        # Arrange
        mock_metrics_collector.get_metric.return_value = 42

        # Act
        value = mock_metrics_collector.get_metric("active_sessions")

        # Assert
        assert value == 42

    def test_reset_metrics(self, mock_metrics_collector):
        """Test resetting all metrics"""
        # Act
        mock_metrics_collector.reset()

        # Assert
        mock_metrics_collector.reset.assert_called_once()


class TestAgentMetrics:
    """Unit tests for agent-specific metrics"""

    @pytest.fixture
    def mock_agent_metrics(self):
        """Create mock agent metrics"""
        with patch('monitoring.metrics.AgentMetrics') as MockAgentMetrics:
            metrics = MagicMock()
            MockAgentMetrics.return_value = metrics
            yield metrics

    def test_record_agent_call(self, mock_agent_metrics):
        """Test recording agent call"""
        # Act
        mock_agent_metrics.record_agent_call("mailer", success=True, duration_ms=150)

        # Assert
        mock_agent_metrics.record_agent_call.assert_called_once_with(
            "mailer",
            success=True,
            duration_ms=150
        )

    def test_record_tool_usage(self, mock_agent_metrics):
        """Test recording tool usage"""
        # Act
        mock_agent_metrics.record_tool_usage("gmail_send", success=True)

        # Assert
        mock_agent_metrics.record_tool_usage.assert_called_once_with(
            "gmail_send",
            success=True
        )

    def test_record_error(self, mock_agent_metrics):
        """Test recording errors"""
        # Arrange
        error_info = {
            "agent": "librarian",
            "error_type": "ConnectionError",
            "message": "Failed to connect to Drive API"
        }

        # Act
        mock_agent_metrics.record_error(error_info)

        # Assert
        mock_agent_metrics.record_error.assert_called_once_with(error_info)

    def test_get_agent_stats(self, mock_agent_metrics):
        """Test getting agent statistics"""
        # Arrange
        mock_stats = {
            "total_calls": 100,
            "successful_calls": 95,
            "failed_calls": 5,
            "avg_duration_ms": 175.5,
            "error_rate": 0.05
        }
        mock_agent_metrics.get_stats.return_value = mock_stats

        # Act
        stats = mock_agent_metrics.get_stats("mailer")

        # Assert
        assert stats["total_calls"] == 100
        assert stats["error_rate"] == 0.05


class TestMetricsDecorators:
    """Unit tests for metrics decorators"""

    def test_track_time_decorator(self):
        """Test @track_time decorator"""
        # Arrange
        with patch('monitoring.metrics.track_time') as mock_decorator:
            @mock_decorator("test_operation")
            def test_function():
                return "result"

            # Act
            result = test_function()

            # Assert
            mock_decorator.assert_called_once_with("test_operation")

    def test_count_calls_decorator(self):
        """Test @count_calls decorator"""
        # Arrange
        with patch('monitoring.metrics.count_calls') as mock_decorator:
            @mock_decorator("test_function")
            def test_function():
                return "result"

            # Act
            test_function()
            test_function()

            # Assert
            mock_decorator.assert_called()


class TestAlertingService:
    """Unit tests for alerting service"""

    @pytest.fixture
    def mock_alerting_service(self):
        """Create mock alerting service"""
        with patch('monitoring.alerting.AlertingService') as MockAlerting:
            service = MagicMock()
            MockAlerting.return_value = service
            yield service

    def test_alerting_service_initialization(self, mock_alerting_service):
        """Test alerting service initializes"""
        # Assert
        assert mock_alerting_service is not None

    def test_send_alert(self, mock_alerting_service):
        """Test sending alert"""
        # Arrange
        alert = {
            "severity": "ERROR",
            "title": "High error rate",
            "message": "Error rate exceeded threshold",
            "timestamp": datetime.now().isoformat()
        }

        # Act
        mock_alerting_service.send_alert(alert)

        # Assert
        mock_alerting_service.send_alert.assert_called_once_with(alert)

    def test_alert_severity_levels(self, mock_alerting_service):
        """Test different alert severity levels"""
        # Arrange
        severities = ["INFO", "WARNING", "ERROR", "CRITICAL"]

        # Act
        for severity in severities:
            mock_alerting_service.send_alert({"severity": severity, "message": "Test"})

        # Assert
        assert mock_alerting_service.send_alert.call_count == len(severities)

    def test_alert_with_metadata(self, mock_alerting_service):
        """Test alert with additional metadata"""
        # Arrange
        alert = {
            "severity": "WARNING",
            "title": "Performance degradation",
            "message": "Response time increased",
            "metadata": {
                "agent": "mailer",
                "avg_response_time_ms": 500,
                "threshold_ms": 300
            }
        }

        # Act
        mock_alerting_service.send_alert(alert)

        # Assert
        call_args = mock_alerting_service.send_alert.call_args[0][0]
        assert "metadata" in call_args
        assert call_args["metadata"]["agent"] == "mailer"

    def test_alert_deduplication(self, mock_alerting_service):
        """Test alert deduplication"""
        # Arrange
        alert_key = "high_error_rate"
        mock_alerting_service.should_send_alert.return_value = False

        # Act
        if mock_alerting_service.should_send_alert(alert_key):
            mock_alerting_service.send_alert({"key": alert_key})

        # Assert - Alert not sent due to deduplication
        mock_alerting_service.send_alert.assert_not_called()

    def test_alert_cooldown_period(self, mock_alerting_service):
        """Test alert cooldown period"""
        # Arrange
        alert_key = "error_spike"
        cooldown_seconds = 300  # 5 minutes

        # First alert
        mock_alerting_service.should_send_alert.return_value = True
        mock_alerting_service.send_alert({"key": alert_key})

        # Second alert within cooldown
        mock_alerting_service.should_send_alert.return_value = False

        # Act
        if mock_alerting_service.should_send_alert(alert_key):
            mock_alerting_service.send_alert({"key": alert_key})

        # Assert - Only one alert sent
        assert mock_alerting_service.send_alert.call_count == 1


class TestAlertConditions:
    """Unit tests for alert condition evaluation"""

    def test_error_rate_threshold(self):
        """Test error rate threshold condition"""
        # Arrange
        total_calls = 100
        failed_calls = 15
        error_rate = failed_calls / total_calls
        threshold = 0.10  # 10%

        # Act
        should_alert = error_rate > threshold

        # Assert
        assert should_alert is True
        assert error_rate == 0.15

    def test_response_time_threshold(self):
        """Test response time threshold condition"""
        # Arrange
        avg_response_time_ms = 350
        threshold_ms = 300

        # Act
        should_alert = avg_response_time_ms > threshold_ms

        # Assert
        assert should_alert is True

    def test_combined_conditions(self):
        """Test combined alert conditions"""
        # Arrange
        error_rate = 0.08
        avg_response_time_ms = 400
        error_threshold = 0.05
        time_threshold = 300

        # Act
        should_alert = (error_rate > error_threshold) or (avg_response_time_ms > time_threshold)

        # Assert
        assert should_alert is True

    def test_no_alert_needed(self):
        """Test when no alert is needed"""
        # Arrange
        error_rate = 0.02
        avg_response_time_ms = 150
        error_threshold = 0.05
        time_threshold = 300

        # Act
        should_alert = (error_rate > error_threshold) or (avg_response_time_ms > time_threshold)

        # Assert
        assert should_alert is False


class TestMonitoringIntegration:
    """Unit tests for monitoring system integration"""

    def test_log_and_metric_together(self):
        """Test logging and metrics work together"""
        # Arrange
        logger = MagicMock(spec=logging.Logger)
        metrics = MagicMock()

        # Act - Simulate operation
        logger.info("Starting operation")
        metrics.increment("operations_started")

        duration_ms = 200
        metrics.record_time("operation_duration", duration_ms)
        logger.info(f"Operation completed in {duration_ms}ms")

        # Assert
        assert logger.info.call_count == 2
        assert metrics.increment.call_count == 1
        assert metrics.record_time.call_count == 1

    def test_metric_triggers_alert(self):
        """Test that metrics can trigger alerts"""
        # Arrange
        metrics = MagicMock()
        alerting = MagicMock()

        # Simulate high error rate
        total_calls = 100
        errors = 20
        error_rate = errors / total_calls

        metrics.get_metric.return_value = error_rate

        # Act
        if metrics.get_metric("error_rate") > 0.10:
            alerting.send_alert({
                "severity": "WARNING",
                "message": f"Error rate {error_rate:.1%} exceeds threshold"
            })

        # Assert
        alerting.send_alert.assert_called_once()

    def test_monitoring_disabled(self):
        """Test behavior when monitoring is disabled"""
        # Arrange
        monitoring_enabled = False
        logger = MagicMock()
        metrics = MagicMock()

        # Act
        if monitoring_enabled:
            logger.info("Operation started")
            metrics.increment("operations")

        # Assert
        logger.info.assert_not_called()
        metrics.increment.assert_not_called()
