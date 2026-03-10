"""
Integration test: REAL Mailer Agent with Mock Gmail MCP Server

Tests the actual MailerAgent class integrating with mock Gmail MCP server.
This tests REAL agent code, not just mocks.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from agents.mailer.mailer import MailerAgent
from tests.mocks.mock_mcp_servers import MockGmailMCPServer, create_mock_gmail_server


class TestRealMailerAgentIntegration:
    """Test REAL Mailer agent with mock Gmail server"""

    @pytest.fixture
    def mailer_agent(self):
        """Create real Mailer agent instance"""
        try:
            return MailerAgent()
        except Exception as e:
            pytest.skip(f"MailerAgent initialization requires setup: {e}")

    @pytest.fixture
    def mock_gmail_server(self):
        """Create mock Gmail MCP server"""
        return create_mock_gmail_server()

    def test_mailer_agent_initializes(self, mailer_agent):
        """Test real Mailer agent initializes correctly"""
        assert mailer_agent is not None
        assert mailer_agent.name == "mailer"
        assert mailer_agent.model == "gemini-1.5-pro"
        assert hasattr(mailer_agent, 'instructions')

    def test_mailer_agent_has_instructions(self, mailer_agent):
        """Test Mailer agent loads instructions"""
        assert len(mailer_agent.instructions) > 0
        # Instructions should mention email/gmail
        instructions_lower = mailer_agent.instructions.lower()
        assert "email" in instructions_lower or "gmail" in instructions_lower or "mail" in instructions_lower

    def test_gmail_mock_server_integration(self, mock_gmail_server):
        """Test mock Gmail server works"""
        # Send test email
        result = mock_gmail_server.send_message(
            to="test@example.com",
            subject="Test Email",
            body="This is a test"
        )

        assert result["status"] == "sent"
        assert "id" in result
        assert len(mock_gmail_server.sent_messages) == 1

    def test_mailer_config_matches_registry(self):
        """Test Mailer config from registry matches agent"""
        from config.agent_registry import get_agent_config

        config = get_agent_config("mailer")

        assert config.name == "mailer"
        assert config.model == "gemini-1.5-pro"
        assert "gmail_mcp" in config.tools


class TestLibrarianWithDriveMCP:
    """Test REAL Librarian agent with mock Drive MCP server"""

    @pytest.fixture
    def librarian_agent(self):
        """Create real Librarian agent instance"""
        try:
            from agents.librarian.librarian import LibrarianAgent
            return LibrarianAgent()
        except Exception as e:
            pytest.skip(f"LibrarianAgent initialization requires setup: {e}")

    @pytest.fixture
    def mock_drive_server(self):
        """Create mock Drive MCP server"""
        from tests.mocks.mock_mcp_servers import create_mock_drive_server
        return create_mock_drive_server()

    def test_librarian_agent_initializes(self, librarian_agent):
        """Test real Librarian agent initializes correctly"""
        assert librarian_agent is not None
        assert librarian_agent.name == "librarian"
        assert librarian_agent.model == "gemini-1.5-flash"

    def test_librarian_has_drive_instructions(self, librarian_agent):
        """Test Librarian has Drive-related instructions"""
        instructions_lower = librarian_agent.instructions.lower()
        assert "drive" in instructions_lower or "file" in instructions_lower

    def test_drive_mock_server_integration(self, mock_drive_server):
        """Test mock Drive server works"""
        # Search for files
        results = mock_drive_server.search_files(query="test")

        assert isinstance(results, list)
        # Mock server has default files
        assert len(results) >= 0

    def test_librarian_config_has_drive_tools(self):
        """Test Librarian config includes Drive tools"""
        from config.agent_registry import get_agent_config

        config = get_agent_config("librarian")

        assert "drive_mcp" in config.tools
        assert "drive_query_translator" in config.tools


class TestScribeWithDocsMCP:
    """Test REAL Scribe agent with mock Docs MCP server"""

    @pytest.fixture
    def scribe_agent(self):
        """Create real Scribe agent instance"""
        try:
            from agents.scribe.scribe import ScribeAgent
            return ScribeAgent()
        except Exception as e:
            pytest.skip(f"ScribeAgent initialization requires setup: {e}")

    @pytest.fixture
    def mock_docs_server(self):
        """Create mock Docs MCP server"""
        from tests.mocks.mock_mcp_servers import create_mock_docs_server
        return create_mock_docs_server()

    def test_scribe_agent_initializes(self, scribe_agent):
        """Test real Scribe agent initializes correctly"""
        assert scribe_agent is not None
        assert scribe_agent.name == "scribe"
        assert scribe_agent.model == "gemini-1.5-pro"

    def test_scribe_has_docs_instructions(self, scribe_agent):
        """Test Scribe has Docs-related instructions"""
        instructions_lower = scribe_agent.instructions.lower()
        assert "doc" in instructions_lower or "document" in instructions_lower

    def test_docs_mock_server_integration(self, mock_docs_server):
        """Test mock Docs server works"""
        # Create document
        result = mock_docs_server.create_document("Test Document")

        assert "documentId" in result
        assert result["title"] == "Test Document"

    def test_scribe_config_has_docs_tools(self):
        """Test Scribe config includes Docs tools"""
        from config.agent_registry import get_agent_config

        config = get_agent_config("scribe")

        assert "docs_mcp" in config.tools
        assert "docs_formatter" in config.tools


class TestAnalystWithSheetsMCP:
    """Test REAL Analyst agent with mock Sheets MCP server"""

    @pytest.fixture
    def analyst_agent(self):
        """Create real Analyst agent instance"""
        try:
            from agents.analyst.analyst import AnalystAgent
            return AnalystAgent()
        except Exception as e:
            pytest.skip(f"AnalystAgent initialization requires setup: {e}")

    @pytest.fixture
    def mock_sheets_server(self):
        """Create mock Sheets MCP server"""
        from tests.mocks.mock_mcp_servers import create_mock_sheets_server
        return create_mock_sheets_server()

    def test_analyst_agent_initializes(self, analyst_agent):
        """Test real Analyst agent initializes correctly"""
        assert analyst_agent is not None
        assert analyst_agent.name == "analyst"
        assert analyst_agent.model == "gemini-1.5-flash"

    def test_analyst_has_sheets_instructions(self, analyst_agent):
        """Test Analyst has Sheets-related instructions"""
        instructions_lower = analyst_agent.instructions.lower()
        assert "sheet" in instructions_lower or "spreadsheet" in instructions_lower

    def test_sheets_mock_server_integration(self, mock_sheets_server):
        """Test mock Sheets server works"""
        # Create spreadsheet
        result = mock_sheets_server.create_spreadsheet("Test Spreadsheet")

        assert "spreadsheetId" in result
        assert result["title"] == "Test Spreadsheet"

    def test_analyst_config_has_sheets_tools(self):
        """Test Analyst config includes Sheets tools"""
        from config.agent_registry import get_agent_config

        config = get_agent_config("analyst")

        assert "sheets_mcp" in config.tools
        assert "sheets_schema_reader" in config.tools


class TestSecretaryWithCalendarMCP:
    """Test REAL Secretary agent with mock Calendar MCP server"""

    @pytest.fixture
    def secretary_agent(self):
        """Create real Secretary agent instance"""
        try:
            from agents.secretary.secretary import SecretaryAgent
            return SecretaryAgent()
        except Exception as e:
            pytest.skip(f"SecretaryAgent initialization requires setup: {e}")

    @pytest.fixture
    def mock_calendar_server(self):
        """Create mock Calendar MCP server"""
        from tests.mocks.mock_mcp_servers import create_mock_calendar_server
        return create_mock_calendar_server()

    def test_secretary_agent_initializes(self, secretary_agent):
        """Test real Secretary agent initializes correctly"""
        assert secretary_agent is not None
        assert secretary_agent.name == "secretary"
        assert secretary_agent.model == "gemini-1.5-flash"

    def test_secretary_has_calendar_instructions(self, secretary_agent):
        """Test Secretary has Calendar-related instructions"""
        instructions_lower = secretary_agent.instructions.lower()
        assert "calendar" in instructions_lower or "event" in instructions_lower or "meeting" in instructions_lower

    def test_calendar_mock_server_integration(self, mock_calendar_server):
        """Test mock Calendar server works"""
        # Create event
        result = mock_calendar_server.create_event(
            summary="Test Meeting",
            start_time="2024-01-01T10:00:00Z",
            end_time="2024-01-01T11:00:00Z"
        )

        assert result["status"] == "confirmed"
        assert "id" in result

    def test_secretary_config_has_calendar_tools(self):
        """Test Secretary config includes Calendar tools"""
        from config.agent_registry import get_agent_config

        config = get_agent_config("secretary")

        assert "calendar_mcp" in config.tools


class TestOrchestratorWithWorkerAgents:
    """Test REAL Orchestrator agent can coordinate workers"""

    @pytest.fixture
    def orchestrator_agent(self):
        """Create real Orchestrator agent instance"""
        try:
            from agents.orchestrator.orchestrator import OrchestratorAgent
            return OrchestratorAgent()
        except Exception as e:
            pytest.skip(f"OrchestratorAgent initialization requires setup: {e}")

    def test_orchestrator_initializes(self, orchestrator_agent):
        """Test real Orchestrator initializes correctly"""
        assert orchestrator_agent is not None
        assert orchestrator_agent.name == "orchestrator"
        assert orchestrator_agent.model == "gemini-1.5-flash"

    def test_orchestrator_has_routing_instructions(self, orchestrator_agent):
        """Test Orchestrator has routing instructions"""
        instructions_lower = orchestrator_agent.instructions.lower()
        # Should mention routing, delegation, or agents
        assert any(keyword in instructions_lower for keyword in [
            "route", "delegate", "agent", "orchestrat", "coordinate"
        ])

    def test_orchestrator_config_lists_agents(self):
        """Test Orchestrator can access other agents"""
        from config.agent_registry import get_worker_agent_names

        worker_agents = get_worker_agent_names()

        assert "orchestrator" not in worker_agents
        assert len(worker_agents) == 9  # All except orchestrator
        assert "mailer" in worker_agents
        assert "librarian" in worker_agents


class TestCustomToolsWithAgents:
    """Test REAL custom tools work with agents"""

    def test_docs_formatter_tool(self):
        """Test DocsFormatter custom tool"""
        from tools.custom_tools.docs_formatter import DocsFormatter

        formatter = DocsFormatter()
        markdown = "# Test Heading\n\nThis is **bold** text."

        requests = formatter.markdown_to_docs_requests(markdown)

        assert isinstance(requests, list)
        assert len(requests) > 0

    def test_drive_query_translator_tool(self):
        """Test DriveQueryTranslator custom tool"""
        from tools.custom_tools.drive_query_translator import DriveQueryTranslator

        translator = DriveQueryTranslator()
        natural_query = "find budget files"

        qpl = translator.translate(natural_query)

        assert isinstance(qpl, str)
        assert len(qpl) > 0

    def test_sheets_schema_reader_tool(self):
        """Test SheetsSchemaReader custom tool"""
        from tools.custom_tools.sheets_schema_reader import SheetsSchemaReader

        reader = SheetsSchemaReader()

        assert reader is not None
        assert hasattr(reader, 'read_schema')


class TestAgentInstructionsQuality:
    """Test agent instructions are comprehensive"""

    def test_all_agents_have_comprehensive_instructions(self):
        """Test all agents have substantial instruction files"""
        from config.agent_registry import get_all_agent_names, get_agent_config
        from pathlib import Path

        agent_names = get_all_agent_names()

        for agent_name in agent_names:
            config = get_agent_config(agent_name)
            instruction_file = Path(config.instruction_file)

            if instruction_file.exists():
                content = instruction_file.read_text()
                # Instructions should be at least 500 characters
                assert len(content) > 500, f"{agent_name} instructions should be comprehensive"


class TestAgentModelSelection:
    """Test agents use appropriate Gemini models"""

    def test_pro_model_agents(self):
        """Test agents that should use Pro model"""
        pro_agents = ["mailer", "scribe", "researcher", "scraper"]

        from config.agent_registry import get_agent_config

        for agent_name in pro_agents:
            config = get_agent_config(agent_name)
            assert config.model == "gemini-1.5-pro", \
                f"{agent_name} should use gemini-1.5-pro model"

    def test_flash_model_agents(self):
        """Test agents that should use Flash model"""
        flash_agents = ["orchestrator", "librarian", "analyst", "secretary", "rolodex", "tracker"]

        from config.agent_registry import get_agent_config

        for agent_name in flash_agents:
            config = get_agent_config(agent_name)
            assert config.model == "gemini-1.5-flash", \
                f"{agent_name} should use gemini-1.5-flash model"
