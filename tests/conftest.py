"""
Pytest Configuration and Fixtures
"""

import pytest
import os
import sys
from unittest.mock import Mock, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment variables"""
    os.environ['ENVIRONMENT'] = 'test'
    os.environ['LOG_LEVEL'] = 'DEBUG'
    yield

@pytest.fixture
def mock_orchestrator():
    """Mock orchestrator fixture - returns ADK orchestrator agent"""
    from agents.adk_agents.orchestrator_adk import create_orchestrator_agent
    return create_orchestrator_agent(sub_agents=[])

@pytest.fixture
def sample_markdown():
    return """# Heading 1\n**bold** and *italic*"""

def pytest_configure(config):
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
