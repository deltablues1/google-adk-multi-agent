"""
Google Docs MCP Toolset

Wrapper za Google Docs operacije
"""

import os
from typing import Optional
from google.genai.types import Tool, FunctionDeclaration
import logging

logger = logging.getLogger(__name__)


def get_docs_mcp_tools() -> list[Tool]:
    """
    Dohvaća Google Docs MCP alate

    Returns:
        Lista Tool objekata za Docs operacije
    """

    tools = [
        Tool(
            function_declarations=[
                FunctionDeclaration(
                    name="docs_create_document",
                    description="Create a new Google Docs document.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "Document title"
                            }
                        },
                        "required": ["title"]
                    }
                ),

                FunctionDeclaration(
                    name="docs_get_document",
                    description="Get the content and metadata of a Google Docs document.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "document_id": {
                                "type": "string",
                                "description": "Document ID from URL"
                            }
                        },
                        "required": ["document_id"]
                    }
                ),

                FunctionDeclaration(
                    name="docs_insert_text",
                    description="Insert text at a specific location in the document.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "document_id": {
                                "type": "string",
                                "description": "Document ID"
                            },
                            "text": {
                                "type": "string",
                                "description": "Text to insert"
                            },
                            "index": {
                                "type": "integer",
                                "description": "Position to insert (1-based). Use 1 for beginning, or get current end index first.",
                                "default": 1
                            }
                        },
                        "required": ["document_id", "text"]
                    }
                ),

                FunctionDeclaration(
                    name="docs_delete_content",
                    description="Delete content from a range in the document.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "document_id": {
                                "type": "string",
                                "description": "Document ID"
                            },
                            "start_index": {
                                "type": "integer",
                                "description": "Start position (1-based)"
                            },
                            "end_index": {
                                "type": "integer",
                                "description": "End position (1-based)"
                            }
                        },
                        "required": ["document_id", "start_index", "end_index"]
                    }
                ),

                FunctionDeclaration(
                    name="docs_batch_update",
                    description="Perform batch updates for complex formatting (headings, bold, lists, etc.). Use this for formatted content.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "document_id": {
                                "type": "string",
                                "description": "Document ID"
                            },
                            "requests": {
                                "type": "array",
                                "items": {"type": "object"},
                                "description": "Array of batch update request objects from docs_formatter tool"
                            }
                        },
                        "required": ["document_id", "requests"]
                    }
                ),

                FunctionDeclaration(
                    name="docs_format_text",
                    description="Apply text formatting (bold, italic, underline, font size, color) to a range.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "document_id": {
                                "type": "string",
                                "description": "Document ID"
                            },
                            "start_index": {
                                "type": "integer",
                                "description": "Start position (1-based)"
                            },
                            "end_index": {
                                "type": "integer",
                                "description": "End position (1-based)"
                            },
                            "bold": {
                                "type": "boolean",
                                "description": "Apply bold formatting",
                            },
                            "italic": {
                                "type": "boolean",
                                "description": "Apply italic formatting",
                            },
                            "underline": {
                                "type": "boolean",
                                "description": "Apply underline",
                            },
                            "font_size": {
                                "type": "integer",
                                "description": "Font size in points",
                            }
                        },
                        "required": ["document_id", "start_index", "end_index"]
                    }
                ),

                FunctionDeclaration(
                    name="docs_insert_image",
                    description="Insert an image into the document from a URL.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "document_id": {
                                "type": "string",
                                "description": "Document ID"
                            },
                            "image_url": {
                                "type": "string",
                                "description": "Public URL of the image"
                            },
                            "index": {
                                "type": "integer",
                                "description": "Position to insert image (1-based)",
                                "default": 1
                            }
                        },
                        "required": ["document_id", "image_url"]
                    }
                ),
            ]
        )
    ]

    logger.info("Docs MCP tools loaded")
    return tools


def get_docs_mcp_server_config() -> dict:
    """
    Dohvaća konfiguraciju za Docs MCP server

    Returns:
        Dictionary s konfiguracijskim parametrima
    """
    return {
        "command": "python",
        "args": ["-m", "tools.mcp_toolsets.docs_mcp"],
        "env": {
            "GOOGLE_APPLICATION_CREDENTIALS": os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
        }
    }
