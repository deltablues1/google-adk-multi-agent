"""
Google Calendar MCP Toolset

Wrapper za Google Calendar operacije
"""

import os
from typing import Optional
from google.genai.types import Tool, FunctionDeclaration
import logging

logger = logging.getLogger(__name__)


def get_calendar_mcp_tools() -> list[Tool]:
    """
    Dohvaća Google Calendar MCP alate

    Returns:
        Lista Tool objekata za Calendar operacije
    """

    tools = [
        Tool(
            function_declarations=[
                FunctionDeclaration(
                    name="calendar_list_events",
                    description="List calendar events within a time range.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "calendar_id": {
                                "type": "string",
                                "description": "Calendar ID (use 'primary' for main calendar)",
                                "default": "primary"
                            },
                            "time_min": {
                                "type": "string",
                                "description": "Start time in RFC3339 format (e.g., '2024-01-01T00:00:00Z')"
                            },
                            "time_max": {
                                "type": "string",
                                "description": "End time in RFC3339 format",
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of events (default: 10)",
                                "default": 10
                            }
                        },
                        "required": ["time_min"]
                    }
                ),

                FunctionDeclaration(
                    name="calendar_get_event",
                    description="Get details of a specific calendar event.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "event_id": {
                                "type": "string",
                                "description": "Calendar event ID"
                            },
                            "calendar_id": {
                                "type": "string",
                                "description": "Calendar ID (default: 'primary')",
                                "default": "primary"
                            }
                        },
                        "required": ["event_id"]
                    }
                ),

                FunctionDeclaration(
                    name="calendar_create_event",
                    description="Create a new calendar event.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "summary": {
                                "type": "string",
                                "description": "Event title/summary"
                            },
                            "start_time": {
                                "type": "string",
                                "description": "Start time in RFC3339 format"
                            },
                            "end_time": {
                                "type": "string",
                                "description": "End time in RFC3339 format"
                            },
                            "description": {
                                "type": "string",
                                "description": "Event description (optional)",
                            },
                            "location": {
                                "type": "string",
                                "description": "Event location (optional)",
                            },
                            "attendees": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of attendee email addresses (optional)",
                            },
                            "calendar_id": {
                                "type": "string",
                                "description": "Calendar ID (default: 'primary')",
                                "default": "primary"
                            }
                        },
                        "required": ["summary", "start_time", "end_time"]
                    }
                ),

                FunctionDeclaration(
                    name="calendar_update_event",
                    description="Update an existing calendar event.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "event_id": {
                                "type": "string",
                                "description": "Calendar event ID"
                            },
                            "summary": {
                                "type": "string",
                                "description": "New event title (optional)",
                            },
                            "start_time": {
                                "type": "string",
                                "description": "New start time in RFC3339 format (optional)",
                            },
                            "end_time": {
                                "type": "string",
                                "description": "New end time in RFC3339 format (optional)",
                            },
                            "description": {
                                "type": "string",
                                "description": "New description (optional)",
                            },
                            "location": {
                                "type": "string",
                                "description": "New location (optional)",
                            },
                            "calendar_id": {
                                "type": "string",
                                "description": "Calendar ID (default: 'primary')",
                                "default": "primary"
                            }
                        },
                        "required": ["event_id"]
                    }
                ),

                FunctionDeclaration(
                    name="calendar_delete_event",
                    description="Delete a calendar event.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "event_id": {
                                "type": "string",
                                "description": "Calendar event ID"
                            },
                            "calendar_id": {
                                "type": "string",
                                "description": "Calendar ID (default: 'primary')",
                                "default": "primary"
                            }
                        },
                        "required": ["event_id"]
                    }
                ),
            ]
        )
    ]

    logger.info("Calendar MCP tools loaded")
    return tools


def get_calendar_mcp_server_config() -> dict:
    """
    Dohvaća konfiguraciju za Calendar MCP server

    Returns:
        Dictionary s konfiguracijskim parametrima
    """
    return {
        "command": "python",
        "args": ["-m", "tools.mcp_toolsets.calendar_mcp"],
        "env": {
            "GOOGLE_APPLICATION_CREDENTIALS": os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
        }
    }
