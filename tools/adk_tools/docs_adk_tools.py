"""
Docs ADK Tools

ADK-compatible wrappers for Google Docs operations:
- Create and manage documents
- Insert and format text
- Batch updates for complex formatting
- Export documents

Includes Markdown-to-Docs formatter for structured content creation.
"""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def _get_credentials():
    """Get OAuth credentials from token file"""
    try:
        from auth.oauth_manager import get_oauth_manager
        oauth_manager = get_oauth_manager()
        creds = oauth_manager.get_credentials()
        if creds and creds.valid:
            return creds
        logger.warning("No valid credentials available for Docs operations")
        return None
    except Exception as e:
        logger.error(f"Failed to get credentials: {e}")
        return None


async def docs_create_document(
    title: str,
    content: Optional[str] = None,
    share: bool = False,
    share_role: str = "reader",
) -> dict:
    """
    Create a new Google Docs document, fill it with content, and optionally share it.

    This is the ONE-CALL way to produce a finished document. When `content` is
    provided it is written into the document (Markdown is auto-formatted into
    headings/bold/lists; on any formatting issue it falls back to plain text).
    When `share=True` the document is shared (anyone with the link can view),
    so emailed links work without an "access denied" error.

    Prefer this single call over create-then-batch_update: it guarantees the
    document is never left empty and the returned URL is immediately usable.

    Args:
        title: Document title
        content: Document body. Plain text or Markdown
            (# headings, **bold**, - lists, [text](url)). Strongly recommended.
        share: If True, share the document as "anyone with link" (default False).
            Note: when a created document is emailed, the mailer auto-shares it
            with the actual recipient (least privilege), so public link-sharing
            is normally unnecessary.
        share_role: Permission when sharing: "reader" (default), "commenter", or "writer".

    Returns:
        Dictionary with document_id, title, document_url, content_inserted,
        shared (bool), and status.
    """
    creds = _get_credentials()
    if creds is None:
        return {"error": "Authentication required"}

    try:
        from tools.api_implementations.docs_api import (
            docs_create_document as docs_create_impl,
            docs_batch_update as docs_batch_impl,
            docs_insert_text as docs_insert_impl,
        )

        # 1. Create the (empty) document first; we insert content ourselves so
        #    we can apply Markdown formatting.
        result = await docs_create_impl(creds, title, None)
        if not isinstance(result, dict) or result.get("error") or not result.get("document_id"):
            return result
        doc_id = result["document_id"]

        # 2. Insert content (Markdown-formatted, with plain-text fallback).
        content_inserted = False
        if content and content.strip():
            try:
                from tools.custom_tools.docs_formatter import DocsFormatter
                requests = DocsFormatter().markdown_to_docs_requests(content)
                if requests:
                    await docs_batch_impl(creds, doc_id, requests)
                    content_inserted = True
            except Exception as fmt_err:
                logger.warning(f"Markdown formatting failed, falling back to plain text: {fmt_err}")
            if not content_inserted:
                await docs_insert_impl(creds, doc_id, content, 1)
                content_inserted = True
        result["content_inserted"] = content_inserted

        # 3. Optionally share so links are accessible to recipients.
        if share:
            try:
                from tools.api_implementations.drive_api import drive_share_file as drive_share_impl
                share_res = await drive_share_impl(creds, doc_id, None, share_role, "anyone")
                result["shared"] = not (isinstance(share_res, dict) and share_res.get("error"))
                result["share_role"] = share_role
            except Exception as share_err:
                logger.error(f"Sharing failed for {doc_id}: {share_err}")
                result["shared"] = False
                result["share_error"] = str(share_err)

        return result
    except Exception as e:
        logger.error(f"Document creation failed: {e}")
        return {"error": str(e), "title": title}


async def docs_get_document(document_id: str, include_suggestions: bool = False) -> dict:
    """
    Get the content and metadata of a Google Docs document.

    Retrieves document title, text content, structure, and formatting information.
    Useful for reading existing documents before updating them.

    Args:
        document_id: Google Docs document ID (from URL)
        include_suggestions: Include suggestions mode changes (default: False)

    Returns:
        Dictionary with document_id, title, text_content, body structure, and metadata
    """
    creds = _get_credentials()
    if creds is None:
        return {"error": "Authentication required"}

    try:
        from tools.api_implementations.docs_api import docs_get_document as docs_get_impl

        result = await docs_get_impl(creds, document_id, include_suggestions)
        return result
    except Exception as e:
        logger.error(f"Failed to get document {document_id}: {e}")
        return {"error": str(e), "document_id": document_id}


async def docs_insert_text(document_id: str, text: str, index: int = 1) -> dict:
    """
    Insert text at a specific location in the document.

    Inserts plain text at the specified index position. For formatted text,
    use docs_batch_update with format_markdown_for_docs instead.

    Args:
        document_id: Document ID
        text: Text to insert
        index: Position to insert (1-based, default: 1 for beginning)

    Returns:
        Dictionary with document_id, inserted_text_length, and status
    """
    creds = _get_credentials()
    if creds is None:
        return {"error": "Authentication required"}

    try:
        from tools.api_implementations.docs_api import docs_insert_text as docs_insert_impl

        result = await docs_insert_impl(creds, document_id, text, index)
        return result
    except Exception as e:
        logger.error(f"Failed to insert text in {document_id}: {e}")
        return {"error": str(e), "document_id": document_id}


async def docs_batch_update(document_id: str, requests: List[Dict[str, Any]]) -> dict:
    """
    Perform batch updates for complex formatting operations.

    Use this for applying multiple formatting operations efficiently:
    - Headings (H1-H6)
    - Bold, italic, underline
    - Lists (ordered, unordered)
    - Paragraph styles
    - Links

    Best practice: Use format_markdown_for_docs to generate requests array
    from Markdown, then pass to this function.

    Args:
        document_id: Document ID
        requests: Array of Docs API batch update request objects

    Returns:
        Dictionary with document_id, updates_applied_count, and status
    """
    creds = _get_credentials()
    if creds is None:
        return {"error": "Authentication required"}

    try:
        from tools.api_implementations.docs_api import docs_batch_update as docs_batch_impl

        result = await docs_batch_impl(creds, document_id, requests)
        return result
    except Exception as e:
        logger.error(f"Batch update failed for {document_id}: {e}")
        return {"error": str(e), "document_id": document_id}


async def docs_format_text(
    document_id: str,
    start_index: int,
    end_index: int,
    bold: Optional[bool] = None,
    italic: Optional[bool] = None,
    underline: Optional[bool] = None,
    font_size: Optional[int] = None
) -> dict:
    """
    Apply text formatting to a specific range in the document.

    Use this for simple formatting operations on existing text.
    For complex formatting, use docs_batch_update instead.

    Args:
        document_id: Document ID
        start_index: Start position (1-based)
        end_index: End position (1-based)
        bold: Apply bold formatting (optional)
        italic: Apply italic formatting (optional)
        underline: Apply underline formatting (optional)
        font_size: Set font size in points (optional)

    Returns:
        Dictionary with document_id, formatted_range, and status
    """
    creds = _get_credentials()
    if creds is None:
        return {"error": "Authentication required"}

    try:
        from tools.api_implementations.docs_api import docs_format_text as docs_format_impl

        result = await docs_format_impl(
            creds, document_id, start_index, end_index,
            bold, italic, underline, font_size
        )
        return result
    except Exception as e:
        logger.error(f"Text formatting failed for {document_id}: {e}")
        return {"error": str(e), "document_id": document_id}


async def format_markdown_for_docs(markdown: str) -> dict:
    """
    Convert Markdown to Google Docs API batch update requests.

    This is a helper tool that converts Markdown syntax to Docs API format.
    Use it to prepare formatted content for docs_batch_update.

    Supported Markdown:
    - Headings: # H1, ## H2, ### H3, etc.
    - Bold: **text** or __text__
    - Italic: *text* or _text_
    - Lists: - item or * item (unordered), 1. item (ordered)
    - Links: [text](url)
    - Paragraphs: Plain text

    Workflow:
    1. Compose content in Markdown
    2. Call format_markdown_for_docs(markdown)
    3. Pass resulting requests to docs_batch_update(document_id, requests)

    Args:
        markdown: Markdown text to convert

    Returns:
        Dictionary with requests array and formatted_length
    """
    try:
        from tools.custom_tools.docs_formatter import DocsFormatter

        formatter = DocsFormatter()
        requests = formatter.markdown_to_docs_requests(markdown)

        return {
            "requests": requests,
            "formatted_length": formatter.current_index - 1,
            "markdown_length": len(markdown),
            "status": "formatted"
        }
    except Exception as e:
        logger.error(f"Markdown formatting failed: {e}")
        return {"error": str(e), "markdown_length": len(markdown)}


def get_docs_adk_tools(credentials=None) -> List:
    """
    Get all Docs ADK tools as plain Python functions.

    ADK automatically wraps these functions as tools based on:
    - Function signature (type hints)
    - Docstring (description and parameter docs)

    Args:
        credentials: Not used - included for API compatibility. Tools use OAuth from token.

    Returns:
        List of docs tool functions
    """
    tools = [
        docs_create_document,
        docs_get_document,
        docs_insert_text,
        docs_batch_update,
        docs_format_text,
        format_markdown_for_docs
    ]

    logger.info(f"Docs ADK tools loaded: {len(tools)} tools")
    return tools


if __name__ == "__main__":
    # Test tool loading
    tools = get_docs_adk_tools()
    print(f"[OK] Docs ADK tools loaded: {len(tools)} tools")

    for tool in tools:
        print(f"   - {tool.__name__}")

    print("\n[CAPABILITIES] Google Docs Operations:")
    print("   - Create new documents")
    print("   - Read document content")
    print("   - Insert and format text")
    print("   - Batch updates for complex formatting")
    print("   - Markdown-to-Docs conversion")
    print("   - Professional document structure")
