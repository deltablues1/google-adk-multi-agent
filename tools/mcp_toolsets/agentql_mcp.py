"""
AgentQL MCP Toolset

Wrapper za AgentQL preciznu DOM ekstrakciju
"""

import os
from typing import Optional
from google.genai.types import Tool, FunctionDeclaration
import logging

logger = logging.getLogger(__name__)


def get_agentql_mcp_tools() -> list[Tool]:
    """
    Dohvaća AgentQL MCP alate

    Returns:
        Lista Tool objekata za AgentQL operacije
    """

    tools = [
        Tool(
            function_declarations=[
                FunctionDeclaration(
                    name="agentql_query",
                    description="Extract structured data from a webpage using natural language query. Returns precise, structured JSON data.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "URL of the webpage to extract data from"
                            },
                            "query": {
                                "type": "string",
                                "description": "Natural language description of what data to extract (e.g., 'product name, price, and reviews')"
                            }
                        },
                        "required": ["url", "query"]
                    }
                ),

                FunctionDeclaration(
                    name="agentql_extract_schema",
                    description="Extract data from a webpage using a JSON schema definition. Best for complex, structured extraction.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "URL of the webpage"
                            },
                            "schema": {
                                "type": "object",
                                "description": "JSON Schema defining the structure to extract"
                            }
                        },
                        "required": ["url", "schema"]
                    }
                ),

                FunctionDeclaration(
                    name="agentql_extract_list",
                    description="Extract a list of items from a webpage (e.g., product listings, search results, articles).",
                    parameters={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "URL of the webpage"
                            },
                            "item_description": {
                                "type": "string",
                                "description": "Description of items to extract (e.g., 'product cards with name and price')"
                            },
                            "max_items": {
                                "type": "integer",
                                "description": "Maximum number of items to extract (default: 10)",
                                "default": 10
                            }
                        },
                        "required": ["url", "item_description"]
                    }
                ),

                FunctionDeclaration(
                    name="agentql_extract_table",
                    description="Extract tabular data from a webpage. Identifies and parses HTML tables or table-like structures.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "URL of the webpage"
                            },
                            "table_description": {
                                "type": "string",
                                "description": "Description of the table to extract (e.g., 'pricing table', 'comparison table')",
                            }
                        },
                        "required": ["url"]
                    }
                ),

                FunctionDeclaration(
                    name="agentql_extract_form",
                    description="Extract form field information from a webpage (field names, types, required status, etc.).",
                    parameters={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "URL of the webpage"
                            },
                            "form_identifier": {
                                "type": "string",
                                "description": "Identifier for the form (e.g., 'contact form', 'registration form')",
                            }
                        },
                        "required": ["url"]
                    }
                ),

                FunctionDeclaration(
                    name="agentql_screenshot",
                    description="Take a screenshot of a webpage. Useful for visual verification or capturing dynamic content.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "URL of the webpage"
                            },
                            "full_page": {
                                "type": "boolean",
                                "description": "Capture full page scroll (default: false - viewport only)",
                                "default": False
                            },
                            "selector": {
                                "type": "string",
                                "description": "CSS selector of specific element to screenshot",
                            }
                        },
                        "required": ["url"]
                    }
                ),
            ]
        )
    ]

    logger.info("AgentQL MCP tools loaded")
    return tools


def get_agentql_mcp_server_config() -> dict:
    """
    Dohvaća konfiguraciju za AgentQL MCP server

    Returns:
        Dictionary s konfiguracijskim parametrima
    """
    return {
        "command": "python",
        "args": ["-m", "tools.mcp_toolsets.agentql_mcp"],
        "env": {
            "AGENTQL_API_KEY": os.getenv("AGENTQL_API_KEY", ""),
        }
    }
