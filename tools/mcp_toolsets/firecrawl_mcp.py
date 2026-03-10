"""
Firecrawl MCP Toolset

Wrapper za Firecrawl web scraping operacije
"""

import os
from typing import Optional
from google.genai.types import Tool, FunctionDeclaration
import logging

logger = logging.getLogger(__name__)


def get_firecrawl_mcp_tools() -> list[Tool]:
    """
    Dohvaća Firecrawl MCP alate

    Returns:
        Lista Tool objekata za web scraping operacije
    """

    tools = [
        Tool(
            function_declarations=[
                FunctionDeclaration(
                    name="firecrawl_scrape",
                    description="Scrape a single URL and extract clean Markdown content, metadata, and links.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "URL to scrape"
                            },
                            "formats": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Output formats: ['markdown', 'html', 'screenshot'] (default: ['markdown'])",
                                "default": ["markdown"]
                            },
                            "only_main_content": {
                                "type": "boolean",
                                "description": "Extract only main content, removing headers/footers/nav (default: true)",
                                "default": True
                            }
                        },
                        "required": ["url"]
                    }
                ),

                FunctionDeclaration(
                    name="firecrawl_crawl",
                    description="Crawl a website starting from a URL, following links recursively up to a limit.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "Starting URL for crawling"
                            },
                            "max_depth": {
                                "type": "integer",
                                "description": "Maximum crawl depth (default: 2)",
                                "default": 2
                            },
                            "max_pages": {
                                "type": "integer",
                                "description": "Maximum number of pages to crawl (default: 10)",
                                "default": 10
                            },
                            "exclude_patterns": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "URL patterns to exclude (regex)",
                            }
                        },
                        "required": ["url"]
                    }
                ),

                FunctionDeclaration(
                    name="firecrawl_search",
                    description="Search the web and scrape top results. Returns clean Markdown content from search results.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query"
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of results to scrape (default: 5)",
                                "default": 5
                            },
                            "search_engine": {
                                "type": "string",
                                "description": "Search engine to use: 'google' or 'bing' (default: 'google')",
                                "default": "google"
                            }
                        },
                        "required": ["query"]
                    }
                ),

                FunctionDeclaration(
                    name="firecrawl_extract",
                    description="Extract structured data from a URL using a schema (JSON Schema).",
                    parameters={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "URL to extract data from"
                            },
                            "schema": {
                                "type": "object",
                                "description": "JSON Schema defining the structure to extract"
                            }
                        },
                        "required": ["url", "schema"]
                    }
                ),
            ]
        )
    ]

    logger.info("Firecrawl MCP tools loaded")
    return tools


def get_firecrawl_mcp_server_config() -> dict:
    """
    Dohvaća konfiguraciju za Firecrawl MCP server

    Returns:
        Dictionary s konfiguracijskim parametrima
    """
    return {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-firecrawl"],
        "env": {
            "FIRECRAWL_API_KEY": os.getenv("FIRECRAWL_API_KEY", ""),
        }
    }
