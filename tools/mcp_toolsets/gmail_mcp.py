"""
Gmail MCP Toolset

Wrapper oko @modelcontextprotocol/server-gmail za Gmail operacije
"""

import os
from typing import Optional
from google.genai.types import Tool, FunctionDeclaration
import logging

logger = logging.getLogger(__name__)


def get_gmail_mcp_tools() -> list[Tool]:
    """
    Dohvaća Gmail MCP alate kao Google ADK Tool objekte

    Returns:
        Lista Tool objekata za Gmail operacije
    """

    tools = [
        Tool(
            function_declarations=[
                FunctionDeclaration(
                    name="gmail_search_threads",
                    description="Search Gmail threads using Gmail search query syntax. Returns list of thread IDs and snippets.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Gmail search query (e.g., 'from:john@example.com', 'subject:meeting', 'is:unread')"
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of threads to return (default: 10)",
                                "default": 10
                            }
                        },
                        "required": ["query"]
                    }
                ),

                FunctionDeclaration(
                    name="gmail_get_thread",
                    description="Get full content of a Gmail thread by ID, including all messages in the thread.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "thread_id": {
                                "type": "string",
                                "description": "Gmail thread ID"
                            }
                        },
                        "required": ["thread_id"]
                    }
                ),

                FunctionDeclaration(
                    name="gmail_send_message",
                    description="Send a new Gmail message. Can be a reply to an existing thread or a new conversation.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "to": {
                                "type": "string",
                                "description": "Recipient email address"
                            },
                            "subject": {
                                "type": "string",
                                "description": "Email subject"
                            },
                            "body": {
                                "type": "string",
                                "description": "Email body (plain text or HTML)"
                            },
                            "thread_id": {
                                "type": "string",
                                "description": "Optional: Thread ID to reply to (makes this a reply)",
                            },
                            "cc": {
                                "type": "string",
                                "description": "Optional: CC email addresses (comma-separated)",
                            },
                            "bcc": {
                                "type": "string",
                                "description": "Optional: BCC email addresses (comma-separated)",
                            }
                        },
                        "required": ["to", "subject", "body"]
                    }
                ),

                FunctionDeclaration(
                    name="gmail_create_draft",
                    description="Create a Gmail draft message without sending it.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "to": {
                                "type": "string",
                                "description": "Recipient email address"
                            },
                            "subject": {
                                "type": "string",
                                "description": "Email subject"
                            },
                            "body": {
                                "type": "string",
                                "description": "Email body (plain text or HTML)"
                            },
                            "cc": {
                                "type": "string",
                                "description": "Optional: CC email addresses (comma-separated)",
                            }
                        },
                        "required": ["to", "subject", "body"]
                    }
                ),

                FunctionDeclaration(
                    name="gmail_modify_thread",
                    description="Modify labels on a Gmail thread (add/remove labels like INBOX, UNREAD, STARRED, etc.)",
                    parameters={
                        "type": "object",
                        "properties": {
                            "thread_id": {
                                "type": "string",
                                "description": "Gmail thread ID"
                            },
                            "add_labels": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Labels to add (e.g., ['STARRED', 'IMPORTANT'])",
                            },
                            "remove_labels": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Labels to remove (e.g., ['UNREAD', 'INBOX'])",
                            }
                        },
                        "required": ["thread_id"]
                    }
                ),

                FunctionDeclaration(
                    name="gmail_list_labels",
                    description="List all Gmail labels (both system and user-created labels).",
                    parameters={
                        "type": "object",
                        "properties": {}
                    }
                ),
            ]
        )
    ]

    logger.info("Gmail MCP tools loaded")
    return tools


def get_gmail_mcp_server_config() -> dict:
    """
    Dohvaća konfiguraciju za Gmail MCP server

    Returns:
        Dictionary s konfiguracijskim parametrima
    """
    return {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-gmail"],
        "env": {
            "GOOGLE_OAUTH_CLIENT_ID": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
            "GOOGLE_OAUTH_CLIENT_SECRET": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
            "GOOGLE_OAUTH_REFRESH_TOKEN": os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN", ""),
        }
    }
