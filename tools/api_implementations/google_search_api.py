"""
Google Search API Implementation

Implements two search strategies:
1. Vertex AI Grounding (primary) - uses Gemini's built-in search grounding
2. Google Custom Search API (fallback) - uses Programmable Search Engine

Automatic fallback: If Vertex AI returns 429 (quota exceeded), falls back to Custom Search.
"""

import logging
import os
import asyncio
from typing import Dict, Any, Optional, List
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# Custom Search API configuration
CUSTOM_SEARCH_API_KEY = os.getenv("GOOGLE_API_KEY")
CUSTOM_SEARCH_ENGINE_ID = os.getenv("GOOGLE_CUSTOM_SEARCH_CX")


async def google_search_grounding(
    credentials,
    query: str,
    max_results: int = 5,
    include_citations: bool = True
) -> Dict[str, Any]:
    """
    Perform web search using Google's Vertex AI Grounding with Search

    This uses Google's built-in grounding feature which:
    - Searches Google's index
    - Returns relevant snippets
    - Automatically includes source citations
    - No separate API key needed (uses Vertex AI credentials)

    Args:
        credentials: Google Cloud credentials (not used - Vertex AI handles auth)
        query: Search query
        max_results: Maximum number of results to return (default: 5)
        include_citations: Whether to include source citations (default: True)

    Returns:
        Dictionary with:
        - query: Original query
        - results: List of search results with snippets and URLs
        - grounding_metadata: Attribution and source information

    Reference:
        https://ai.google.dev/gemini-api/docs/grounding
        https://google.github.io/adk-docs/grounding/google_search_grounding/
    """
    try:
        logger.info(f"Executing Google Search Grounding: {query}")

        # Configure Vertex AI client
        from tools.google_api_client import get_vertex_ai_config
        config = get_vertex_ai_config()

        client = genai.Client(
            vertexai=True,
            project=config.get("project_id"),
            location=config.get("location", "global")
        )

        # Create grounding tool configuration
        # This tells Gemini to use Google Search for grounding
        google_search_tool = types.Tool(
            google_search=types.GoogleSearch()
        )

        # Generate content with grounding
        # The model will automatically search and cite sources
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Search the web and answer: {query}",
            config=types.GenerateContentConfig(
                tools=[google_search_tool],
                response_modalities=["TEXT"],
            )
        )

        # Extract search results and grounding metadata
        result_text = response.text if hasattr(response, 'text') else ""

        # Extract grounding metadata (citations)
        grounding_metadata = {}
        if hasattr(response, 'candidates') and len(response.candidates) > 0:
            candidate = response.candidates[0]
            if hasattr(candidate, 'grounding_metadata'):
                grounding_metadata = {
                    'grounding_support': candidate.grounding_metadata
                }

        # Parse grounding chunks to extract source URLs
        sources = []
        if grounding_metadata and hasattr(grounding_metadata.get('grounding_support'), 'grounding_chunks'):
            for chunk in grounding_metadata['grounding_support'].grounding_chunks:
                if hasattr(chunk, 'web'):
                    sources.append({
                        'url': chunk.web.uri,
                        'title': chunk.web.title if hasattr(chunk.web, 'title') else None
                    })

        result = {
            "query": query,
            "answer": result_text,
            "sources": sources,
            "source_count": len(sources),
            "grounding_metadata": str(grounding_metadata) if grounding_metadata else None
        }

        logger.info(f"Google Search completed: {len(sources)} sources found")
        return result

    except Exception as e:
        error_str = str(e)
        logger.error(f"Google Search Grounding failed: {e}")

        # Check if this is a quota error (429) - trigger fallback
        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
            logger.info("Vertex AI quota exhausted, attempting Custom Search fallback...")
            fallback_result = await google_custom_search(
                query=query,
                num_results=max_results
            )
            if fallback_result and not fallback_result.get("error"):
                return fallback_result

        return {
            "query": query,
            "error": str(e),
            "answer": None,
            "sources": [],
            "source_count": 0
        }


async def google_custom_search(
    query: str,
    num_results: int = 10
) -> Dict[str, Any]:
    """
    Perform web search using Google Custom Search API (Programmable Search Engine)

    This is a reliable fallback when Vertex AI Grounding hits quota limits.

    Requirements:
        - GOOGLE_API_KEY environment variable
        - GOOGLE_CUSTOM_SEARCH_CX environment variable (Search Engine ID)

    Get your Search Engine ID from: https://programmablesearchengine.google.com/

    Args:
        query: Search query
        num_results: Number of results (max 10 per request)

    Returns:
        Dictionary with search results
    """
    try:
        if not CUSTOM_SEARCH_API_KEY:
            return {
                "query": query,
                "error": "GOOGLE_API_KEY not configured",
                "sources": [],
                "source_count": 0
            }

        if not CUSTOM_SEARCH_ENGINE_ID:
            return {
                "query": query,
                "error": "GOOGLE_CUSTOM_SEARCH_CX not configured. Create a Custom Search Engine at https://programmablesearchengine.google.com/",
                "sources": [],
                "source_count": 0
            }

        import aiohttp

        logger.info(f"Executing Google Custom Search: {query}")

        # Build the Custom Search API URL
        base_url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": CUSTOM_SEARCH_API_KEY,
            "cx": CUSTOM_SEARCH_ENGINE_ID,
            "q": query,
            "num": min(num_results, 10)  # API max is 10
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(base_url, params=params) as response:
                if response.status == 429:
                    logger.error("Custom Search API quota also exhausted")
                    return {
                        "query": query,
                        "error": "Both Vertex AI and Custom Search API quotas exhausted. Try again later.",
                        "sources": [],
                        "source_count": 0
                    }

                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Custom Search API error: {response.status} - {error_text}")
                    return {
                        "query": query,
                        "error": f"Custom Search API error: {response.status}",
                        "sources": [],
                        "source_count": 0
                    }

                data = await response.json()

        # Parse results
        sources = []
        items = data.get("items", [])

        for item in items:
            sources.append({
                "url": item.get("link"),
                "title": item.get("title"),
                "snippet": item.get("snippet")
            })

        # Build a summary answer from snippets
        answer_parts = [f"Search results for '{query}':\n"]
        for i, source in enumerate(sources[:5], 1):
            answer_parts.append(f"{i}. {source['title']}")
            if source.get('snippet'):
                answer_parts.append(f"   {source['snippet']}")
            answer_parts.append(f"   URL: {source['url']}\n")

        result = {
            "query": query,
            "answer": "\n".join(answer_parts),
            "sources": sources,
            "source_count": len(sources),
            "search_method": "custom_search_api"
        }

        logger.info(f"Custom Search completed: {len(sources)} results found")
        return result

    except ImportError:
        logger.error("aiohttp not installed. Run: pip install aiohttp")
        return {
            "query": query,
            "error": "aiohttp library required. Run: pip install aiohttp",
            "sources": [],
            "source_count": 0
        }
    except Exception as e:
        logger.error(f"Custom Search failed: {e}")
        return {
            "query": query,
            "error": str(e),
            "sources": [],
            "source_count": 0
        }


async def google_search_simple(
    credentials,
    query: str,
    num_results: int = 10
) -> Dict[str, Any]:
    """
    Simple web search that returns just URLs and snippets

    Uses Custom Search API directly for reliability (avoids Vertex AI quota issues).

    Args:
        credentials: Google Cloud credentials (not used, kept for API consistency)
        query: Search query
        num_results: Number of results to return

    Returns:
        Dictionary with search results
    """
    try:
        logger.info(f"Executing simple Google Search: {query}")

        # Use Vertex AI Grounding as primary search method
        full_result = await google_search_grounding(
            credentials=credentials,
            query=f"Find information about: {query}",
            max_results=num_results
        )

        return {
            "query": query,
            "results": full_result.get("sources", []),
            "result_count": full_result.get("source_count", 0),
            "search_method": full_result.get("search_method", "vertex_ai_grounding")
        }

    except Exception as e:
        logger.error(f"Simple Google Search failed: {e}")
        return {
            "query": query,
            "error": str(e),
            "results": [],
            "result_count": 0
        }


def register_google_search_tools(tool_registry) -> None:
    """
    Register Google Search tools in the tool registry

    Args:
        tool_registry: ToolRegistry instance
    """
    # Register grounding-based search
    tool_registry.register_tool(
        name="google_search_grounding",
        function=google_search_grounding,
        description="Search the web using Google's Vertex AI Grounding. Returns AI-generated answer with cited sources.",
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
        },
        requires_auth=False,  # Uses Vertex AI credentials automatically
        auth_type="vertex_ai"
    )

    # Register simple search
    tool_registry.register_tool(
        name="google_search_simple",
        function=google_search_simple,
        description="Simple web search that returns URLs and snippets without AI summarization.",
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
        },
        requires_auth=False,
        auth_type="vertex_ai"
    )

    # Register Custom Search API (direct, reliable)
    tool_registry.register_tool(
        name="google_custom_search",
        function=google_custom_search,
        description="Search the web using Google Custom Search API (Programmable Search Engine). More reliable than Grounding, doesn't hit Vertex AI quotas.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results (max: 10)",
                    "default": 10
                }
            },
            "required": ["query"]
        },
        requires_auth=False,
        auth_type="api_key"
    )

    # Log configuration status
    if CUSTOM_SEARCH_ENGINE_ID:
        logger.info(f"Custom Search API configured (cx: {CUSTOM_SEARCH_ENGINE_ID[:8]}...)")
    else:
        logger.warning("GOOGLE_CUSTOM_SEARCH_CX not set - Custom Search fallback unavailable")

    logger.info("Google Search tools registered successfully")
