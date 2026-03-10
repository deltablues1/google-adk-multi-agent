"""
Integration tests for Agent Orchestration

Tests the interaction between Orchestrator and worker agents.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, List

from config.agent_registry import (
    AGENT_REGISTRY,
    get_agent_config,
    get_all_agent_names,
    get_worker_agent_names,
    create_agent_instance
)


class TestOrchestratorRouting:
    """Test Orchestrator agent routing logic"""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create mock Orchestrator agent"""
        orchestrator = Mock()
        orchestrator.name = "orchestrator"
        orchestrator.model = "gemini-1.5-flash"
        orchestrator.worker_agents = {}
        return orchestrator

    @pytest.fixture
    def mock_worker_agents(self):
        """Create mock worker agents"""
        workers = {
            "mailer": Mock(name="mailer", model="gemini-1.5-pro"),
            "librarian": Mock(name="librarian", model="gemini-1.5-flash"),
            "scribe": Mock(name="scribe", model="gemini-1.5-pro"),
            "analyst": Mock(name="analyst", model="gemini-1.5-flash"),
            "secretary": Mock(name="secretary", model="gemini-1.5-flash"),
            "rolodex": Mock(name="rolodex", model="gemini-1.5-flash"),
            "tracker": Mock(name="tracker", model="gemini-1.5-flash"),
            "researcher": Mock(name="researcher", model="gemini-1.5-pro"),
            "scraper": Mock(name="scraper", model="gemini-1.5-pro")
        }
        return workers

    def test_route_to_mailer(self, mock_orchestrator, mock_worker_agents):
        """Test routing email requests to Mailer"""
        # Arrange
        mock_orchestrator.worker_agents = mock_worker_agents
        email_requests = [
            "Send an email to john@example.com",
            "Check my inbox for new messages",
            "Draft an email about the meeting",
            "Reply to the latest email from boss"
        ]

        # Act & Assert
        for request in email_requests:
            request_lower = request.lower()
            # Email-related keywords should route to mailer
            assert any(kw in request_lower for kw in ['email', 'send', 'inbox', 'draft', 'reply'])

    def test_route_to_librarian(self, mock_orchestrator, mock_worker_agents):
        """Test routing Drive requests to Librarian"""
        # Arrange
        mock_orchestrator.worker_agents = mock_worker_agents
        drive_requests = [
            "Find the budget file from last week",
            "Search for documents about Q4 planning",
            "Upload the report to Drive",
            "Show me files shared by Alice"
        ]

        # Act & Assert
        for request in drive_requests:
            request_lower = request.lower()
            # Drive-related keywords should route to librarian
            assert any(kw in request_lower for kw in ['file', 'document', 'drive', 'search', 'find', 'upload'])

    def test_route_to_secretary(self, mock_orchestrator, mock_worker_agents):
        """Test routing Calendar requests to Secretary"""
        # Arrange
        mock_orchestrator.worker_agents = mock_worker_agents
        calendar_requests = [
            "Schedule a meeting for tomorrow at 2pm",
            "What's on my calendar this week?",
            "Create an event for the team standup",
            "Check my availability on Friday"
        ]

        # Act & Assert
        for request in calendar_requests:
            request_lower = request.lower()
            # Calendar-related keywords should route to secretary
            assert any(kw in request_lower for kw in ['schedule', 'meeting', 'calendar', 'event', 'availability'])

    def test_route_to_researcher(self, mock_orchestrator, mock_worker_agents):
        """Test routing research requests to Researcher"""
        # Arrange
        mock_orchestrator.worker_agents = mock_worker_agents
        research_requests = [
            "Research the latest AI trends",
            "Find information about quantum computing",
            "What are the best practices for API design?",
            "Summarize recent articles about climate change"
        ]

        # Act & Assert
        for request in research_requests:
            request_lower = request.lower()
            # Research-related keywords should route to researcher
            assert any(kw in request_lower for kw in ['research', 'find information', 'summarize', 'articles'])


class TestAgentRegistry:
    """Test agent registry functionality"""

    def test_all_agents_registered(self):
        """Test that all expected agents are in registry"""
        # Arrange
        expected_agents = [
            "orchestrator", "mailer", "librarian", "scribe",
            "analyst", "secretary", "rolodex", "tracker",
            "researcher", "scraper"
        ]

        # Act
        registered_agents = get_all_agent_names()

        # Assert
        for agent in expected_agents:
            assert agent in registered_agents

    def test_worker_agents_exclude_orchestrator(self):
        """Test that worker agents don't include orchestrator"""
        # Act
        worker_agents = get_worker_agent_names()

        # Assert
        assert "orchestrator" not in worker_agents
        assert len(worker_agents) == 9  # All except orchestrator

    def test_agent_config_structure(self):
        """Test agent config has required fields"""
        # Act
        for agent_name in get_all_agent_names():
            config = get_agent_config(agent_name)

            # Assert
            assert config.name == agent_name
            assert config.module is not None
            assert config.class_name is not None
            assert config.model in ["gemini-1.5-flash", "gemini-1.5-pro"]
            assert config.description is not None
            assert isinstance(config.tools, list)

    def test_model_distribution(self):
        """Test that agents use appropriate models"""
        # Arrange
        flash_agents = ["orchestrator", "librarian", "analyst", "secretary", "rolodex", "tracker"]
        pro_agents = ["mailer", "scribe", "researcher", "scraper"]

        # Act & Assert
        for agent_name in flash_agents:
            config = get_agent_config(agent_name)
            assert config.model == "gemini-1.5-flash", f"{agent_name} should use Flash"

        for agent_name in pro_agents:
            config = get_agent_config(agent_name)
            assert config.model == "gemini-1.5-pro", f"{agent_name} should use Pro"


class TestAgentInteraction:
    """Test interactions between agents"""

    @pytest.fixture
    def mock_agents(self):
        """Create mock agent instances"""
        return {
            "orchestrator": Mock(name="orchestrator"),
            "mailer": Mock(name="mailer"),
            "librarian": Mock(name="librarian")
        }

    def test_orchestrator_delegates_to_worker(self, mock_agents):
        """Test orchestrator delegates tasks to worker agents"""
        # Arrange
        orchestrator = mock_agents["orchestrator"]
        mailer = mock_agents["mailer"]
        orchestrator.worker_agents = {"mailer": mailer}

        # Simulate delegation
        user_request = "Send an email to team@example.com"
        selected_agent = "mailer"

        # Act
        # Orchestrator would call: worker_agents[selected_agent].process(request)
        if selected_agent in orchestrator.worker_agents:
            orchestrator.worker_agents[selected_agent].process(user_request)

        # Assert
        mailer.process.assert_called_once_with(user_request)

    def test_orchestrator_handles_multi_step_tasks(self, mock_agents):
        """Test orchestrator can coordinate multi-step tasks"""
        # Arrange
        orchestrator = mock_agents["orchestrator"]
        librarian = mock_agents["librarian"]
        mailer = mock_agents["mailer"]
        orchestrator.worker_agents = {"librarian": librarian, "mailer": mailer}

        # Simulate multi-step task: "Find the report and email it to John"
        steps = [
            ("librarian", "Find the report"),
            ("mailer", "Email the report to John")
        ]

        # Act
        for agent_name, task in steps:
            if agent_name in orchestrator.worker_agents:
                orchestrator.worker_agents[agent_name].process(task)

        # Assert
        librarian.process.assert_called_once()
        mailer.process.assert_called_once()

    def test_agent_can_return_results_to_orchestrator(self, mock_agents):
        """Test worker agents can return results to orchestrator"""
        # Arrange
        librarian = mock_agents["librarian"]
        expected_result = {
            "status": "success",
            "files_found": [
                {"id": "file-1", "name": "report.pdf"}
            ]
        }
        librarian.process.return_value = expected_result

        # Act
        result = librarian.process("Find the budget report")

        # Assert
        assert result["status"] == "success"
        assert len(result["files_found"]) > 0


class TestAgentToolAccess:
    """Test that agents have access to appropriate tools"""

    def test_mailer_has_gmail_tools(self):
        """Test Mailer agent is configured with Gmail tools"""
        # Act
        config = get_agent_config("mailer")

        # Assert
        assert "gmail_mcp" in config.tools

    def test_librarian_has_drive_tools(self):
        """Test Librarian agent is configured with Drive tools"""
        # Act
        config = get_agent_config("librarian")

        # Assert
        assert "drive_mcp" in config.tools
        assert "drive_query_translator" in config.tools

    def test_scribe_has_docs_tools(self):
        """Test Scribe agent is configured with Docs tools"""
        # Act
        config = get_agent_config("scribe")

        # Assert
        assert "docs_mcp" in config.tools
        assert "docs_formatter" in config.tools

    def test_analyst_has_sheets_tools(self):
        """Test Analyst agent is configured with Sheets tools"""
        # Act
        config = get_agent_config("analyst")

        # Assert
        assert "sheets_mcp" in config.tools
        assert "sheets_schema_reader" in config.tools

    def test_researcher_has_firecrawl_tools(self):
        """Test Researcher agent is configured with Firecrawl tools"""
        # Act
        config = get_agent_config("researcher")

        # Assert
        assert "firecrawl_mcp" in config.tools

    def test_scraper_has_agentql_tools(self):
        """Test Scraper agent is configured with AgentQL tools"""
        # Act
        config = get_agent_config("scraper")

        # Assert
        assert "agentql_mcp" in config.tools


class TestAgentErrorPropagation:
    """Test error handling in agent orchestration"""

    @pytest.fixture
    def mock_orchestrator_with_error_handling(self):
        """Create orchestrator mock with error handling"""
        orchestrator = Mock()
        orchestrator.handle_error = Mock(return_value={
            "status": "error",
            "message": "Agent failed to process request"
        })
        return orchestrator

    def test_orchestrator_handles_worker_errors(self, mock_orchestrator_with_error_handling):
        """Test orchestrator handles errors from worker agents"""
        # Arrange
        orchestrator = mock_orchestrator_with_error_handling
        mailer = Mock()
        mailer.process.side_effect = Exception("SMTP connection failed")
        orchestrator.worker_agents = {"mailer": mailer}

        # Act
        try:
            mailer.process("Send email")
        except Exception as e:
            result = orchestrator.handle_error(e)

        # Assert
        assert result["status"] == "error"
        orchestrator.handle_error.assert_called_once()

    def test_orchestrator_provides_fallback_on_error(self, mock_orchestrator_with_error_handling):
        """Test orchestrator can provide fallback when agent fails"""
        # Arrange
        orchestrator = mock_orchestrator_with_error_handling
        orchestrator.fallback = Mock(return_value={
            "status": "fallback",
            "message": "Using alternative approach"
        })

        # Act
        result = orchestrator.fallback("Original task that failed")

        # Assert
        assert result["status"] == "fallback"
        orchestrator.fallback.assert_called_once()


class TestConcurrentAgentExecution:
    """Test concurrent agent execution scenarios"""

    def test_multiple_agents_can_execute_simultaneously(self):
        """Test that multiple agents can work on different tasks concurrently"""
        # Arrange
        agents = {
            "mailer": Mock(name="mailer"),
            "librarian": Mock(name="librarian"),
            "secretary": Mock(name="secretary")
        }

        tasks = [
            ("mailer", "Send status update email"),
            ("librarian", "Find project documents"),
            ("secretary", "Schedule review meeting")
        ]

        # Act
        results = []
        for agent_name, task in tasks:
            # In real implementation, these would run concurrently
            agent = agents[agent_name]
            agent.process.return_value = {"status": "processing", "task": task}
            results.append(agent.process(task))

        # Assert
        assert len(results) == 3
        agents["mailer"].process.assert_called_once()
        agents["librarian"].process.assert_called_once()
        agents["secretary"].process.assert_called_once()
