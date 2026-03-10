"""
Google Sheets MCP Toolset

Wrapper za Google Sheets operacije
"""

import os
from typing import Optional
from google.genai.types import Tool, FunctionDeclaration
import logging

logger = logging.getLogger(__name__)


def get_sheets_mcp_tools() -> list[Tool]:
    """
    Dohvaća Google Sheets MCP alate

    Returns:
        Lista Tool objekata za Sheets operacije
    """

    tools = [
        Tool(
            function_declarations=[
                FunctionDeclaration(
                    name="sheets_get_spreadsheet",
                    description="Get metadata about a spreadsheet (sheet names, properties, etc.)",
                    parameters={
                        "type": "object",
                        "properties": {
                            "spreadsheet_id": {
                                "type": "string",
                                "description": "Spreadsheet ID from URL"
                            }
                        },
                        "required": ["spreadsheet_id"]
                    }
                ),

                FunctionDeclaration(
                    name="sheets_get_values",
                    description="Read data from a specific range in a spreadsheet.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "spreadsheet_id": {
                                "type": "string",
                                "description": "Spreadsheet ID"
                            },
                            "range": {
                                "type": "string",
                                "description": "A1 notation range (e.g., 'Sheet1!A1:D10')"
                            },
                            "value_render_option": {
                                "type": "string",
                                "description": "How values should be rendered: FORMATTED_VALUE, UNFORMATTED_VALUE, or FORMULA",
                                "default": "FORMATTED_VALUE"
                            }
                        },
                        "required": ["spreadsheet_id", "range"]
                    }
                ),

                FunctionDeclaration(
                    name="sheets_update_values",
                    description="Write data to a specific range in a spreadsheet.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "spreadsheet_id": {
                                "type": "string",
                                "description": "Spreadsheet ID"
                            },
                            "range": {
                                "type": "string",
                                "description": "A1 notation range (e.g., 'Sheet1!A1:D10')"
                            },
                            "values": {
                                "type": "array",
                                "items": {
                                    "type": "array",
                                    "items": {"type": "string"}
                                },
                                "description": "2D array of values to write"
                            },
                            "value_input_option": {
                                "type": "string",
                                "description": "How input data should be interpreted: RAW or USER_ENTERED",
                                "default": "USER_ENTERED"
                            }
                        },
                        "required": ["spreadsheet_id", "range", "values"]
                    }
                ),

                FunctionDeclaration(
                    name="sheets_append_values",
                    description="Append rows to the end of a sheet.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "spreadsheet_id": {
                                "type": "string",
                                "description": "Spreadsheet ID"
                            },
                            "range": {
                                "type": "string",
                                "description": "Sheet name or range (e.g., 'Sheet1' or 'Sheet1!A:Z')"
                            },
                            "values": {
                                "type": "array",
                                "items": {
                                    "type": "array",
                                    "items": {"type": "string"}
                                },
                                "description": "2D array of values to append"
                            }
                        },
                        "required": ["spreadsheet_id", "range", "values"]
                    }
                ),

                FunctionDeclaration(
                    name="sheets_clear_values",
                    description="Clear values in a specific range.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "spreadsheet_id": {
                                "type": "string",
                                "description": "Spreadsheet ID"
                            },
                            "range": {
                                "type": "string",
                                "description": "A1 notation range to clear"
                            }
                        },
                        "required": ["spreadsheet_id", "range"]
                    }
                ),

                FunctionDeclaration(
                    name="sheets_create_spreadsheet",
                    description="Create a new spreadsheet.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "Spreadsheet title"
                            },
                            "sheet_names": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional: Names of sheets to create (default: ['Sheet1'])",
                            }
                        },
                        "required": ["title"]
                    }
                ),

                FunctionDeclaration(
                    name="sheets_batch_update",
                    description="Perform batch updates (formatting, adding sheets, etc.)",
                    parameters={
                        "type": "object",
                        "properties": {
                            "spreadsheet_id": {
                                "type": "string",
                                "description": "Spreadsheet ID"
                            },
                            "requests": {
                                "type": "array",
                                "items": {"type": "object"},
                                "description": "Array of batch update request objects"
                            }
                        },
                        "required": ["spreadsheet_id", "requests"]
                    }
                ),
            ]
        )
    ]

    logger.info("Sheets MCP tools loaded")
    return tools


def get_sheets_mcp_server_config() -> dict:
    """
    Dohvaća konfiguraciju za Sheets MCP server

    Returns:
        Dictionary s konfiguracijskim parametrima
    """
    return {
        "command": "python",
        "args": ["-m", "tools.mcp_toolsets.sheets_mcp"],
        "env": {
            "GOOGLE_APPLICATION_CREDENTIALS": os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
        }
    }
