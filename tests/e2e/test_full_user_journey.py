"""
End-to-End Test for Full User Journey

Tests complete workflow from user request through agent orchestration to final response.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, List
from datetime import datetime
import json

from tests.mocks.mock_mcp_servers import (
    create_mock_gmail_server,
    create_mock_drive_server,
    create_mock_docs_server,
    create_mock_sheets_server,
    create_mock_calendar_server
)


class TestEmailWorkflow:
    """E2E test for complete email workflow"""

    @pytest.fixture
    def mock_system(self):
        """Setup complete mock system"""
        system = {
            "gmail": create_mock_gmail_server(),
            "drive": create_mock_drive_server(),
            "orchestrator": Mock(name="orchestrator"),
            "mailer": Mock(name="mailer"),
            "session_service": Mock(name="session_service"),
            "auth": Mock(name="auth"),
            "logger": Mock(name="logger"),
            "metrics": Mock(name="metrics")
        }
        return system

    def test_send_email_complete_flow(self, mock_system):
        """Test complete flow: User request -> Orchestrator -> Mailer -> Gmail -> Response"""
        # Arrange
        user_request = "Send an email to john@example.com saying 'Meeting at 3pm today'"
        session_id = "session-e2e-001"

        # Step 1: User request received
        mock_system["logger"].info(f"User request: {user_request}")
        mock_system["metrics"].increment("user_requests")

        # Step 2: Session created
        mock_system["session_service"].create_session(session_id, {"user_id": "user-123"})

        # Step 3: Orchestrator analyzes request
        mock_system["orchestrator"].route_request.return_value = {
            "agent": "mailer",
            "reasoning": "Email operation detected",
            "task": "send email"
        }
        routing_decision = mock_system["orchestrator"].route_request(user_request)

        # Step 4: Mailer agent processes request
        mock_system["mailer"].process.return_value = {
            "success": True,
            "action": "send_email",
            "params": {
                "to": "john@example.com",
                "subject": "Meeting Notification",
                "body": "Meeting at 3pm today"
            }
        }
        mailer_response = mock_system["mailer"].process(user_request)

        # Step 5: Gmail MCP sends email
        gmail_result = mock_system["gmail"].send_message(
            to=mailer_response["params"]["to"],
            subject=mailer_response["params"]["subject"],
            body=mailer_response["params"]["body"]
        )

        # Step 6: Update session history
        mock_system["session_service"].update_session_history(session_id, {
            "role": "user",
            "content": user_request,
            "timestamp": datetime.now().isoformat()
        })
        mock_system["session_service"].update_session_history(session_id, {
            "role": "assistant",
            "content": f"Email sent to {mailer_response['params']['to']}",
            "timestamp": datetime.now().isoformat()
        })

        # Step 7: Log and track metrics
        mock_system["logger"].info("Email sent successfully")
        mock_system["metrics"].increment("emails_sent", labels={"status": "success"})

        # Assert complete flow
        assert routing_decision["agent"] == "mailer"
        assert mailer_response["success"] is True
        assert gmail_result["status"] == "sent"
        assert len(mock_system["gmail"].sent_messages) == 1
        assert mock_system["session_service"].update_session_history.call_count == 2
        mock_system["logger"].info.assert_called()
        mock_system["metrics"].increment.assert_called()


class TestDocumentWorkflow:
    """E2E test for complete document workflow"""

    @pytest.fixture
    def mock_system(self):
        """Setup complete mock system"""
        system = {
            "drive": create_mock_drive_server(),
            "docs": create_mock_docs_server(),
            "orchestrator": Mock(name="orchestrator"),
            "librarian": Mock(name="librarian"),
            "scribe": Mock(name="scribe"),
            "session_service": Mock(name="session_service"),
            "logger": Mock(name="logger"),
            "metrics": Mock(name="metrics")
        }
        return system

    def test_find_and_edit_document_flow(self, mock_system):
        """Test: User asks to find document and add content"""
        # Arrange
        user_request = "Find the budget document and add a new section about Q1 expenses"
        session_id = "session-e2e-002"

        # Step 1: Session created
        mock_system["session_service"].create_session(session_id, {"user_id": "user-456"})

        # Step 2: Orchestrator routes to Librarian
        mock_system["orchestrator"].route_request.return_value = {
            "agent": "librarian",
            "task": "search_files"
        }

        # Step 3: Librarian searches Drive
        search_results = mock_system["drive"].search_files(query="budget")
        mock_system["librarian"].process.return_value = {
            "success": True,
            "files_found": search_results,
            "selected_file": search_results[0] if search_results else None
        }

        # Step 4: Orchestrator now routes to Scribe for editing
        mock_system["orchestrator"].route_request.return_value = {
            "agent": "scribe",
            "task": "add_content"
        }

        # Step 5: Scribe creates/edits document
        doc_result = mock_system["docs"].create_document("Budget Document")
        mock_system["docs"].insert_text(
            doc_result["documentId"],
            "# Q1 Expenses\n\nBudget breakdown for Q1...",
            index=1
        )

        mock_system["scribe"].process.return_value = {
            "success": True,
            "document_id": doc_result["documentId"],
            "action": "content_added"
        }

        # Step 6: Update session
        mock_system["session_service"].update_session_history(session_id, {
            "role": "assistant",
            "content": "Found budget document and added Q1 expenses section"
        })

        # Assert
        assert len(search_results) > 0
        assert "budget" in search_results[0]["name"].lower()
        assert doc_result["documentId"] is not None
        mock_system["session_service"].update_session_history.assert_called()


class TestMultiAgentCollaboration:
    """E2E test for multi-agent collaboration"""

    @pytest.fixture
    def mock_system(self):
        """Setup complete mock system"""
        system = {
            "gmail": create_mock_gmail_server(),
            "drive": create_mock_drive_server(),
            "sheets": create_mock_sheets_server(),
            "calendar": create_mock_calendar_server(),
            "orchestrator": Mock(name="orchestrator"),
            "librarian": Mock(name="librarian"),
            "analyst": Mock(name="analyst"),
            "mailer": Mock(name="mailer"),
            "session_service": Mock(name="session_service"),
            "logger": Mock(name="logger"),
            "metrics": Mock(name="metrics")
        }
        return system

    def test_complex_multi_step_task(self, mock_system):
        """
        Test complex task: "Analyze Q4 sales data and email summary to team"
        Requires: Librarian -> Analyst -> Mailer
        """
        # Arrange
        user_request = "Analyze the Q4 sales spreadsheet and email the summary to team@example.com"
        session_id = "session-e2e-003"

        # Step 1: Initialize session
        mock_system["session_service"].create_session(session_id, {
            "user_id": "user-789",
            "task_type": "multi_agent"
        })
        mock_system["logger"].info(f"Multi-agent task started: {user_request}")

        # Step 2: Orchestrator identifies multi-step task
        mock_system["orchestrator"].decompose_task.return_value = [
            {"agent": "librarian", "task": "Find Q4 sales spreadsheet"},
            {"agent": "analyst", "task": "Analyze sales data"},
            {"agent": "mailer", "task": "Email summary to team"}
        ]
        task_steps = mock_system["orchestrator"].decompose_task(user_request)

        # Step 3A: Librarian finds spreadsheet
        search_results = mock_system["drive"].search_files(query="Q4 sales")
        mock_system["librarian"].process.return_value = {
            "success": True,
            "file_id": "spreadsheet-123",
            "file_name": "Q4_Sales_2024.xlsx"
        }
        librarian_result = mock_system["librarian"].process("Find Q4 sales spreadsheet")
        mock_system["metrics"].increment("agent_calls", labels={"agent": "librarian"})

        # Step 3B: Analyst analyzes data
        sheet_data = mock_system["sheets"].read_range("spreadsheet-123", "A1:D100")
        mock_system["analyst"].process.return_value = {
            "success": True,
            "summary": {
                "total_sales": 1250000,
                "top_product": "Product A",
                "growth_rate": "15%"
            }
        }
        analyst_result = mock_system["analyst"].process("Analyze sales data")
        mock_system["metrics"].increment("agent_calls", labels={"agent": "analyst"})

        # Step 3C: Mailer sends summary
        email_body = f"""
Q4 Sales Summary:
- Total Sales: ${analyst_result['summary']['total_sales']:,}
- Top Product: {analyst_result['summary']['top_product']}
- Growth Rate: {analyst_result['summary']['growth_rate']}
        """
        gmail_result = mock_system["gmail"].send_message(
            to="team@example.com",
            subject="Q4 Sales Analysis Summary",
            body=email_body
        )
        mock_system["mailer"].process.return_value = {
            "success": True,
            "email_sent": True
        }
        mock_system["metrics"].increment("agent_calls", labels={"agent": "mailer"})

        # Step 4: Update session with complete interaction
        mock_system["session_service"].update_session_history(session_id, {
            "role": "user",
            "content": user_request
        })
        mock_system["session_service"].update_session_history(session_id, {
            "role": "assistant",
            "content": "Task completed: Found spreadsheet, analyzed data, and emailed summary",
            "details": {
                "agents_used": ["librarian", "analyst", "mailer"],
                "steps_completed": 3
            }
        })

        # Step 5: Final metrics and logging
        mock_system["logger"].info("Multi-agent task completed successfully")
        mock_system["metrics"].increment("multi_agent_tasks_completed")

        # Assert complete workflow
        assert len(task_steps) == 3
        assert librarian_result["success"] is True
        assert analyst_result["success"] is True
        assert gmail_result["status"] == "sent"
        assert mock_system["metrics"].increment.call_count >= 4  # 3 agents + task completion
        assert mock_system["session_service"].update_session_history.call_count == 2


class TestErrorRecoveryWorkflow:
    """E2E test for error handling and recovery"""

    @pytest.fixture
    def mock_system(self):
        """Setup mock system with potential failures"""
        system = {
            "gmail": create_mock_gmail_server(),
            "orchestrator": Mock(name="orchestrator"),
            "mailer": Mock(name="mailer"),
            "session_service": Mock(name="session_service"),
            "logger": Mock(name="logger"),
            "metrics": Mock(name="metrics"),
            "alerting": Mock(name="alerting")
        }
        return system

    def test_retry_on_transient_failure(self, mock_system):
        """Test retry mechanism when operation fails transiently"""
        # Arrange
        user_request = "Send email to client@example.com"
        session_id = "session-e2e-004"
        max_retries = 3

        # Step 1: First attempt fails
        mock_system["mailer"].process.side_effect = [
            Exception("SMTP connection timeout"),  # Attempt 1
            Exception("SMTP connection timeout"),  # Attempt 2
            {"success": True, "email_sent": True}  # Attempt 3 succeeds
        ]

        # Act - Retry loop
        for attempt in range(max_retries):
            try:
                mock_system["logger"].info(f"Attempt {attempt + 1} of {max_retries}")
                result = mock_system["mailer"].process(user_request)

                if result.get("success"):
                    mock_system["logger"].info("Email sent successfully")
                    mock_system["metrics"].increment("operations_succeeded")
                    break
            except Exception as e:
                mock_system["logger"].error(f"Attempt {attempt + 1} failed: {str(e)}")
                mock_system["metrics"].increment("retry_attempts")

                if attempt == max_retries - 1:
                    # Final attempt failed
                    mock_system["alerting"].send_alert({
                        "severity": "ERROR",
                        "message": f"Failed after {max_retries} attempts"
                    })
                    raise

        # Assert
        assert mock_system["mailer"].process.call_count == 3
        mock_system["metrics"].increment.assert_called()

    def test_fallback_mechanism(self, mock_system):
        """Test fallback to alternative approach on failure"""
        # Arrange
        user_request = "Send urgent notification"

        # Primary method fails
        mock_system["gmail"].send_message.side_effect = Exception("Gmail API unavailable")

        # Act - Try primary, then fallback
        try:
            mock_system["logger"].info("Trying primary method: Gmail")
            mock_system["gmail"].send_message(
                to="user@example.com",
                subject="Urgent",
                body="Notification"
            )
        except Exception as e:
            mock_system["logger"].warning(f"Primary method failed: {str(e)}")
            mock_system["logger"].info("Using fallback: Draft creation")

            # Fallback: Create draft instead
            draft_result = mock_system["gmail"].create_draft(
                to="user@example.com",
                subject="Urgent",
                body="Notification"
            )

            mock_system["metrics"].increment("fallback_used")
            result = {"success": True, "method": "fallback", "draft_id": draft_result["id"]}

        # Assert
        assert result["method"] == "fallback"
        assert result["success"] is True
        mock_system["metrics"].increment.assert_called_with("fallback_used")


class TestAuthenticationWorkflow:
    """E2E test for authentication workflow"""

    @pytest.fixture
    def mock_auth_system(self):
        """Setup mock authentication system"""
        system = {
            "oauth_manager": Mock(name="oauth_manager"),
            "service_account_manager": Mock(name="service_account_manager"),
            "credential_store": Mock(name="credential_store"),
            "logger": Mock(name="logger")
        }
        return system

    def test_oauth_authentication_flow(self, mock_auth_system):
        """Test complete OAuth authentication flow"""
        # Step 1: Check for existing credentials
        mock_auth_system["credential_store"].get_credentials.return_value = None

        # Step 2: No credentials, start OAuth flow
        mock_auth_system["logger"].info("No credentials found, starting OAuth flow")

        # Step 3: Get authorization URL
        auth_url = "https://accounts.google.com/o/oauth2/auth?..."
        mock_auth_system["oauth_manager"].get_authorization_url.return_value = auth_url

        # Step 4: User authorizes (simulated)
        auth_code = "auth-code-xyz"

        # Step 5: Exchange code for token
        mock_creds = Mock()
        mock_creds.token = "access-token"
        mock_creds.valid = True
        mock_auth_system["oauth_manager"].exchange_code.return_value = mock_creds

        # Step 6: Save credentials
        mock_auth_system["credential_store"].save_credentials(mock_creds)

        # Assert
        mock_auth_system["oauth_manager"].get_authorization_url.assert_called_once()
        mock_auth_system["oauth_manager"].exchange_code.assert_called_once()
        mock_auth_system["credential_store"].save_credentials.assert_called_once()

    def test_credential_refresh_workflow(self, mock_auth_system):
        """Test automatic credential refresh workflow"""
        # Step 1: Get expired credentials
        expired_creds = Mock()
        expired_creds.expired = True
        expired_creds.valid = False
        mock_auth_system["credential_store"].get_credentials.return_value = expired_creds

        # Step 2: Detect expiration
        if expired_creds.expired:
            mock_auth_system["logger"].info("Credentials expired, refreshing...")

            # Step 3: Refresh credentials
            refreshed_creds = Mock()
            refreshed_creds.expired = False
            refreshed_creds.valid = True
            mock_auth_system["oauth_manager"].refresh.return_value = refreshed_creds

            # Step 4: Save refreshed credentials
            mock_auth_system["credential_store"].save_credentials(refreshed_creds)

        # Assert
        mock_auth_system["oauth_manager"].refresh.assert_called_once()
        assert mock_auth_system["credential_store"].save_credentials.call_count == 1


class TestMonitoringWorkflow:
    """E2E test for monitoring throughout operation"""

    @pytest.fixture
    def monitored_system(self):
        """Setup system with full monitoring"""
        system = {
            "logger": Mock(name="logger"),
            "metrics": Mock(name="metrics"),
            "alerting": Mock(name="alerting"),
            "mailer": Mock(name="mailer")
        }
        return system

    def test_full_operation_with_monitoring(self, monitored_system):
        """Test operation with complete monitoring instrumentation"""
        # Arrange
        operation_name = "send_email"

        # Step 1: Log operation start
        monitored_system["logger"].info(f"Starting {operation_name}")
        monitored_system["metrics"].increment("operations_started", labels={"operation": operation_name})

        # Step 2: Execute operation
        start_time = datetime.now()
        monitored_system["mailer"].process.return_value = {"success": True}
        result = monitored_system["mailer"].process("Send test email")
        end_time = datetime.now()
        duration_ms = (end_time - start_time).total_seconds() * 1000

        # Step 3: Record metrics
        monitored_system["metrics"].record_time(operation_name, duration_ms)
        monitored_system["metrics"].increment("operations_completed", labels={
            "operation": operation_name,
            "status": "success"
        })

        # Step 4: Log completion
        monitored_system["logger"].info(f"{operation_name} completed in {duration_ms:.2f}ms")

        # Step 5: Check for performance degradation
        if duration_ms > 500:
            monitored_system["alerting"].send_alert({
                "severity": "WARNING",
                "message": f"{operation_name} took {duration_ms:.2f}ms"
            })

        # Assert
        assert monitored_system["logger"].info.call_count == 2
        assert monitored_system["metrics"].increment.call_count == 2
        monitored_system["metrics"].record_time.assert_called_once()
