"""
Google Tasks MCP Toolset

Wrapper za Google Tasks API operacije
"""

import os
from typing import Optional
from google.genai.types import Tool, FunctionDeclaration
import logging

logger = logging.getLogger(__name__)


def get_tasks_mcp_tools() -> list[Tool]:
    """
    Dohvaća Google Tasks MCP alate

    Returns:
        Lista Tool objekata za Tasks operacije
    """

    tools = [
        Tool(
            function_declarations=[
                FunctionDeclaration(
                    name="tasks_list_tasklists",
                    description="List all task lists (projects/categories).",
                    parameters={
                        "type": "object",
                        "properties": {}
                    }
                ),

                FunctionDeclaration(
                    name="tasks_get_tasklist",
                    description="Get details of a specific task list.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "tasklist_id": {
                                "type": "string",
                                "description": "Task list ID"
                            }
                        },
                        "required": ["tasklist_id"]
                    }
                ),

                FunctionDeclaration(
                    name="tasks_create_tasklist",
                    description="Create a new task list (project/category).",
                    parameters={
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "Task list title"
                            }
                        },
                        "required": ["title"]
                    }
                ),

                FunctionDeclaration(
                    name="tasks_list",
                    description="List all tasks in a specific task list.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "tasklist_id": {
                                "type": "string",
                                "description": "Task list ID (use 'default' for primary list)"
                            },
                            "show_completed": {
                                "type": "boolean",
                                "description": "Include completed tasks (default: false)",
                                "default": False
                            },
                            "show_hidden": {
                                "type": "boolean",
                                "description": "Include hidden tasks (default: false)",
                                "default": False
                            }
                        },
                        "required": ["tasklist_id"]
                    }
                ),

                FunctionDeclaration(
                    name="tasks_get",
                    description="Get details of a specific task.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "tasklist_id": {
                                "type": "string",
                                "description": "Task list ID"
                            },
                            "task_id": {
                                "type": "string",
                                "description": "Task ID"
                            }
                        },
                        "required": ["tasklist_id", "task_id"]
                    }
                ),

                FunctionDeclaration(
                    name="tasks_create",
                    description="Create a new task in a task list.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "tasklist_id": {
                                "type": "string",
                                "description": "Task list ID (use 'default' for primary list)"
                            },
                            "title": {
                                "type": "string",
                                "description": "Task title"
                            },
                            "notes": {
                                "type": "string",
                                "description": "Task notes/description",
                            },
                            "due": {
                                "type": "string",
                                "description": "Due date in RFC3339 format (e.g., '2024-01-15T00:00:00Z')",
                            }
                        },
                        "required": ["tasklist_id", "title"]
                    }
                ),

                FunctionDeclaration(
                    name="tasks_update",
                    description="Update an existing task.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "tasklist_id": {
                                "type": "string",
                                "description": "Task list ID"
                            },
                            "task_id": {
                                "type": "string",
                                "description": "Task ID"
                            },
                            "title": {
                                "type": "string",
                                "description": "Updated task title",
                            },
                            "notes": {
                                "type": "string",
                                "description": "Updated notes",
                            },
                            "due": {
                                "type": "string",
                                "description": "Updated due date (RFC3339 format)",
                            },
                            "status": {
                                "type": "string",
                                "description": "Task status: 'needsAction' or 'completed'",
                            }
                        },
                        "required": ["tasklist_id", "task_id"]
                    }
                ),

                FunctionDeclaration(
                    name="tasks_complete",
                    description="Mark a task as completed.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "tasklist_id": {
                                "type": "string",
                                "description": "Task list ID"
                            },
                            "task_id": {
                                "type": "string",
                                "description": "Task ID to complete"
                            }
                        },
                        "required": ["tasklist_id", "task_id"]
                    }
                ),

                FunctionDeclaration(
                    name="tasks_delete",
                    description="Delete a task permanently.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "tasklist_id": {
                                "type": "string",
                                "description": "Task list ID"
                            },
                            "task_id": {
                                "type": "string",
                                "description": "Task ID to delete"
                            }
                        },
                        "required": ["tasklist_id", "task_id"]
                    }
                ),

                FunctionDeclaration(
                    name="tasks_move",
                    description="Move a task to a different position or parent in the list.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "tasklist_id": {
                                "type": "string",
                                "description": "Task list ID"
                            },
                            "task_id": {
                                "type": "string",
                                "description": "Task ID to move"
                            },
                            "parent": {
                                "type": "string",
                                "description": "New parent task ID (for subtasks)",
                            },
                            "previous": {
                                "type": "string",
                                "description": "Previous sibling task ID (for ordering)",
                            }
                        },
                        "required": ["tasklist_id", "task_id"]
                    }
                ),
            ]
        )
    ]

    logger.info("Tasks MCP tools loaded")
    return tools


def get_tasks_mcp_server_config() -> dict:
    """
    Dohvaća konfiguraciju za Tasks MCP server

    Returns:
        Dictionary s konfiguracijskim parametrima
    """
    return {
        "command": "python",
        "args": ["-m", "tools.mcp_toolsets.tasks_mcp"],
        "env": {
            "GOOGLE_APPLICATION_CREDENTIALS": os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
        }
    }
