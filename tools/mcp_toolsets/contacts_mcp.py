"""
Google Contacts MCP Toolset

Wrapper za Google People API (Contacts) operacije
"""

import os
from typing import Optional
from google.genai.types import Tool, FunctionDeclaration
import logging

logger = logging.getLogger(__name__)


def get_contacts_mcp_tools() -> list[Tool]:
    """
    Dohvaća Google Contacts MCP alate

    Returns:
        Lista Tool objekata za Contacts operacije
    """

    tools = [
        Tool(
            function_declarations=[
                FunctionDeclaration(
                    name="contacts_search",
                    description="Search for contacts by name, email, or phone number.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query (name, email, or phone)"
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of results (default: 10)",
                                "default": 10
                            }
                        },
                        "required": ["query"]
                    }
                ),

                FunctionDeclaration(
                    name="contacts_get",
                    description="Get detailed information about a specific contact by resource name.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "resource_name": {
                                "type": "string",
                                "description": "Contact resource name (e.g., 'people/c1234567890')"
                            }
                        },
                        "required": ["resource_name"]
                    }
                ),

                FunctionDeclaration(
                    name="contacts_create",
                    description="Create a new contact.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "given_name": {
                                "type": "string",
                                "description": "First name"
                            },
                            "family_name": {
                                "type": "string",
                                "description": "Last name"
                            },
                            "email": {
                                "type": "string",
                                "description": "Email address",
                            },
                            "phone": {
                                "type": "string",
                                "description": "Phone number",
                            },
                            "company": {
                                "type": "string",
                                "description": "Company/organization name",
                            },
                            "job_title": {
                                "type": "string",
                                "description": "Job title",
                            }
                        },
                        "required": ["given_name"]
                    }
                ),

                FunctionDeclaration(
                    name="contacts_update",
                    description="Update an existing contact's information.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "resource_name": {
                                "type": "string",
                                "description": "Contact resource name"
                            },
                            "given_name": {
                                "type": "string",
                                "description": "Updated first name",
                            },
                            "family_name": {
                                "type": "string",
                                "description": "Updated last name",
                            },
                            "email": {
                                "type": "string",
                                "description": "Updated email address",
                            },
                            "phone": {
                                "type": "string",
                                "description": "Updated phone number",
                            },
                            "company": {
                                "type": "string",
                                "description": "Updated company name",
                            },
                            "job_title": {
                                "type": "string",
                                "description": "Updated job title",
                            }
                        },
                        "required": ["resource_name"]
                    }
                ),

                FunctionDeclaration(
                    name="contacts_delete",
                    description="Delete a contact.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "resource_name": {
                                "type": "string",
                                "description": "Contact resource name to delete"
                            }
                        },
                        "required": ["resource_name"]
                    }
                ),

                FunctionDeclaration(
                    name="contacts_list",
                    description="List all contacts in the user's address book.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of contacts to return (default: 100)",
                                "default": 100
                            },
                            "sort_order": {
                                "type": "string",
                                "description": "Sort order: 'LAST_MODIFIED_ASCENDING' or 'LAST_MODIFIED_DESCENDING'",
                                "default": "LAST_MODIFIED_DESCENDING"
                            }
                        }
                    }
                ),

                FunctionDeclaration(
                    name="contacts_resolve_email",
                    description="Find email address for a person by name. Useful when you have a name but need the email.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Person's name to search for"
                            }
                        },
                        "required": ["name"]
                    }
                ),
            ]
        )
    ]

    logger.info("Contacts MCP tools loaded")
    return tools


def get_contacts_mcp_server_config() -> dict:
    """
    Dohvaća konfiguraciju za Contacts MCP server

    Returns:
        Dictionary s konfiguracijskim parametrima
    """
    return {
        "command": "python",
        "args": ["-m", "tools.mcp_toolsets.contacts_mcp"],
        "env": {
            "GOOGLE_APPLICATION_CREDENTIALS": os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
        }
    }
