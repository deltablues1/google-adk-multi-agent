"""
Google Drive MCP Toolset

Wrapper za Google Drive operacije
"""

import os
from typing import Optional
from google.genai.types import Tool, FunctionDeclaration
import logging

logger = logging.getLogger(__name__)


def get_drive_mcp_tools() -> list[Tool]:
    """
    Dohvaća Google Drive MCP alate

    Returns:
        Lista Tool objekata za Drive operacije
    """

    tools = [
        Tool(
            function_declarations=[
                FunctionDeclaration(
                    name="drive_search_files",
                    description="Search for files in Google Drive using Drive Query Language (QPL) or natural language.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query (can be QPL or natural language, will be translated)"
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of files to return (default: 10)",
                                "default": 10
                            },
                            "order_by": {
                                "type": "string",
                                "description": "Sort order (e.g., 'modifiedTime desc', 'name')",
                            }
                        },
                        "required": ["query"]
                    }
                ),

                FunctionDeclaration(
                    name="drive_get_file",
                    description="Get metadata and content of a specific file by ID.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "file_id": {
                                "type": "string",
                                "description": "Google Drive file ID"
                            },
                            "include_content": {
                                "type": "boolean",
                                "description": "Whether to download and include file content (default: false)",
                                "default": False
                            }
                        },
                        "required": ["file_id"]
                    }
                ),

                FunctionDeclaration(
                    name="drive_upload_file",
                    description="Upload a new file to Google Drive.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "file_name": {
                                "type": "string",
                                "description": "Name of the file"
                            },
                            "content": {
                                "type": "string",
                                "description": "File content (text or base64 encoded for binary)"
                            },
                            "mime_type": {
                                "type": "string",
                                "description": "MIME type of the file"
                            },
                            "parent_folder_id": {
                                "type": "string",
                                "description": "Optional: Parent folder ID (default: root)",
                            }
                        },
                        "required": ["file_name", "content", "mime_type"]
                    }
                ),

                FunctionDeclaration(
                    name="drive_update_file",
                    description="Update an existing file's content or metadata.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "file_id": {
                                "type": "string",
                                "description": "Google Drive file ID"
                            },
                            "content": {
                                "type": "string",
                                "description": "New file content (optional)",
                            },
                            "name": {
                                "type": "string",
                                "description": "New file name (optional)",
                            }
                        },
                        "required": ["file_id"]
                    }
                ),

                FunctionDeclaration(
                    name="drive_delete_file",
                    description="Move a file to trash (soft delete).",
                    parameters={
                        "type": "object",
                        "properties": {
                            "file_id": {
                                "type": "string",
                                "description": "Google Drive file ID"
                            }
                        },
                        "required": ["file_id"]
                    }
                ),

                FunctionDeclaration(
                    name="drive_share_file",
                    description="Share a file with users or make it publicly accessible.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "file_id": {
                                "type": "string",
                                "description": "Google Drive file ID"
                            },
                            "email": {
                                "type": "string",
                                "description": "Email address to share with (omit for public sharing)",
                            },
                            "role": {
                                "type": "string",
                                "description": "Permission role: 'reader', 'writer', or 'commenter' (default: 'reader')",
                                "default": "reader"
                            },
                            "type": {
                                "type": "string",
                                "description": "Permission type: 'user', 'group', 'domain', or 'anyone' (default: 'user')",
                                "default": "user"
                            }
                        },
                        "required": ["file_id"]
                    }
                ),

                FunctionDeclaration(
                    name="drive_create_folder",
                    description="Create a new folder in Google Drive.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "folder_name": {
                                "type": "string",
                                "description": "Name of the folder"
                            },
                            "parent_folder_id": {
                                "type": "string",
                                "description": "Optional: Parent folder ID (default: root)",
                            }
                        },
                        "required": ["folder_name"]
                    }
                ),

                FunctionDeclaration(
                    name="drive_move_file",
                    description="Move a file to a different folder.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "file_id": {
                                "type": "string",
                                "description": "Google Drive file ID"
                            },
                            "new_parent_id": {
                                "type": "string",
                                "description": "ID of the destination folder"
                            }
                        },
                        "required": ["file_id", "new_parent_id"]
                    }
                ),
            ]
        )
    ]

    logger.info("Drive MCP tools loaded")
    return tools


def get_drive_mcp_server_config() -> dict:
    """
    Dohvaća konfiguraciju za Drive MCP server

    Returns:
        Dictionary s konfiguracijskim parametrima
    """
    return {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-gdrive"],
        "env": {
            "GOOGLE_OAUTH_CLIENT_ID": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
            "GOOGLE_OAUTH_CLIENT_SECRET": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
            "GOOGLE_OAUTH_REFRESH_TOKEN": os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN", ""),
        }
    }
