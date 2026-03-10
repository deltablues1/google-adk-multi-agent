"""
Research MCP Toolset

Wrapper za Deep Research tools:
- Google Search Grounding (Vertex AI built-in)
- YouTube Transcript extraction
- Web Scraping (BeautifulSoup)
"""

import os
from typing import Optional
from google.genai.types import Tool, FunctionDeclaration
import logging

logger = logging.getLogger(__name__)


def get_research_mcp_tools() -> list[Tool]:
    """
    Dohvaća Research MCP alate

    Returns:
        Lista Tool objekata za deep research operacije
    """

    tools = [
        Tool(
            function_declarations=[
                # ========== GOOGLE SEARCH GROUNDING ==========
                FunctionDeclaration(
                    name="google_search_grounding",
                    description="Search the web using Google's Vertex AI Grounding. Returns AI-generated answer with cited sources. Best for: fact-checking, recent information, news.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query"
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of results (default: 5)",
                                "default": 5
                            },
                            "include_citations": {
                                "type": "boolean",
                                "description": "Include source citations (default: true)",
                                "default": True
                            }
                        },
                        "required": ["query"]
                    }
                ),

                FunctionDeclaration(
                    name="google_search_simple",
                    description="Simple web search that returns URLs and snippets without AI summarization. Best for: finding URLs to scrape, discovering resources.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query"
                            },
                            "num_results": {
                                "type": "integer",
                                "description": "Number of results to return (default: 10)",
                                "default": 10
                            }
                        },
                        "required": ["query"]
                    }
                ),

                # ========== YOUTUBE TRANSCRIPT ==========
                FunctionDeclaration(
                    name="youtube_get_transcript",
                    description="Get transcript (captions/subtitles) from a YouTube video. Works with Croatian and English videos. Best for: analyzing video content, extracting information from talks/presentations.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "YouTube video URL or video ID"
                            },
                            "languages": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Preferred languages for transcript (default: ['hr', 'en'])",
                                "default": ["hr", "en"]
                            },
                            "preserve_formatting": {
                                "type": "boolean",
                                "description": "Keep timestamps and segment structure (default: false)",
                                "default": False
                            }
                        },
                        "required": ["url"]
                    }
                ),

                # ========== WEB SCRAPING ==========
                FunctionDeclaration(
                    name="scrape_url",
                    description="Scrape content from a URL. Optimized for Croatian news portals (index.hr, jutarnji.hr, 24sata.hr, vecernji.hr). Extracts article text, titles, and links. Best for: reading full articles, extracting detailed content.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "URL to scrape"
                            },
                            "extract_type": {
                                "type": "string",
                                "description": "Type of extraction: 'article' (default), 'all_text', or 'links'",
                                "enum": ["article", "all_text", "links"],
                                "default": "article"
                            },
                            "return_html": {
                                "type": "boolean",
                                "description": "Return raw HTML as well (default: false)",
                                "default": False
                            }
                        },
                        "required": ["url"]
                    }
                ),

                FunctionDeclaration(
                    name="scrape_multiple_urls",
                    description="Scrape multiple URLs in parallel. Efficient for processing search results or news aggregation. Best for: batch processing, comparing multiple sources.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "urls": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of URLs to scrape"
                            },
                            "extract_type": {
                                "type": "string",
                                "description": "Type of extraction: 'article' (default), 'all_text', or 'links'",
                                "enum": ["article", "all_text", "links"],
                                "default": "article"
                            }
                        },
                        "required": ["urls"]
                    }
                ),
            ]
        )
    ]

    logger.info("Research MCP tools loaded")
    return tools


def get_research_mcp_capabilities() -> dict:
    """
    Vraća opis mogućnosti Research agenta

    Returns:
        Dictionary s opisom capabilities
    """
    return {
        "web_search": {
            "description": "Google Search with Vertex AI Grounding",
            "capabilities": [
                "Real-time web search",
                "Automatic source citation",
                "AI-generated summaries",
                "Recent information access"
            ],
            "no_api_key_needed": True
        },
        "youtube_analysis": {
            "description": "YouTube Transcript Extraction",
            "capabilities": [
                "Extract video transcripts",
                "Croatian and English support",
                "Timestamp preservation",
                "Free access (no API key)"
            ],
            "no_api_key_needed": True
        },
        "web_scraping": {
            "description": "Web Content Extraction",
            "capabilities": [
                "Article extraction",
                "Croatian news portal optimization",
                "Parallel URL processing",
                "Link extraction"
            ],
            "optimized_for": [
                "index.hr",
                "jutarnji.hr",
                "24sata.hr",
                "vecernji.hr",
                "rtl.hr"
            ],
            "no_api_key_needed": True
        }
    }
