"""
Configuration module for Google Workspace ADK

Provides agent registry, auth configuration, and MCP server configuration
"""

from .agent_registry import (
    AgentConfig,
    AGENT_REGISTRY,
    get_agent_config,
    get_all_agent_names,
    get_worker_agent_names,
    create_agent_instance,
    generate_orchestrator_routing_guide,
)

from .auth_config import (
    AuthConfig,
    OAuthConfig,
    ServiceAccountConfig,
    get_auth_config,
)

from .mcp_config import (
    MCPServerConfig,
    MCP_SERVER_REGISTRY,
    get_mcp_server_config,
    get_all_mcp_servers,
)

__all__ = [
    # Agent Registry
    'AgentConfig',
    'AGENT_REGISTRY',
    'get_agent_config',
    'get_all_agent_names',
    'get_worker_agent_names',
    'create_agent_instance',
    'generate_orchestrator_routing_guide',
    # Auth Config
    'AuthConfig',
    'OAuthConfig',
    'ServiceAccountConfig',
    'get_auth_config',
    # MCP Config
    'MCPServerConfig',
    'MCP_SERVER_REGISTRY',
    'get_mcp_server_config',
    'get_all_mcp_servers',
]
