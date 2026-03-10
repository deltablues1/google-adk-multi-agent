"""
Gmail ADK Tools

ADK-compatible wrappers for Gmail operations.
"""

from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# AUTHENTICATION HELPER
# ============================================================================

def _get_credentials():
    """Get OAuth credentials from token file"""
    try:
        from auth.oauth_manager import get_oauth_manager
        oauth_manager = get_oauth_manager()
        creds = oauth_manager.get_credentials()
        if creds and creds.valid:
            return creds
        logger.warning("No valid credentials available for Gmail operations")
        return None
    except Exception as e:
        logger.error(f"Failed to get credentials: {e}")
        return None


# ============================================================================
# GMAIL TOOLS
# ============================================================================

async def gmail_search_threads(query: str, max_results: int = 10) -> dict:
    """
    Search Gmail threads using Gmail search query syntax.

    Use this to find emails matching specific criteria. Supports Gmail's
    powerful search operators like 'from:', 'subject:', 'is:unread', etc.

    Args:
        query: Gmail search query. Examples:
               - 'from:john@example.com' - emails from specific sender
               - 'subject:meeting' - emails with meeting in subject
               - 'is:unread' - unread emails
               - 'has:attachment' - emails with attachments
        max_results: Maximum number of threads to return (default: 10)

    Returns:
        Dictionary containing:
            - threads: List of thread objects with id, snippet, from, to, subject
            - result_size_estimate: Total number of matching threads
            - query: The search query used
    """
    creds = _get_credentials()
    if creds is None:
        return {
            "error": "Authentication required. Run: python tools/oauth_cli.py --auth",
            "status": "unauthenticated"
        }

    try:
        from tools.api_implementations.gmail_api import gmail_search_threads as gmail_search_impl
        result = await gmail_search_impl(creds, query, max_results)
        logger.info(f"Searched Gmail: '{query}' - found {result.get('result_size_estimate', 0)} threads")
        return result
    except Exception as e:
        logger.error(f"gmail_search_threads failed: {e}")
        return {"error": str(e), "status": "error"}


async def gmail_get_thread(thread_id: str) -> dict:
    """
    Get full content of a Gmail thread by ID.

    Retrieves all messages in a thread including full email bodies.

    Args:
        thread_id: Gmail thread ID (obtained from gmail_search_threads)

    Returns:
        Dictionary containing:
            - id: Thread ID
            - messages: List of message objects with from, to, subject, body
            - message_count: Number of messages in thread
    """
    creds = _get_credentials()
    if creds is None:
        return {
            "error": "Authentication required. Run: python tools/oauth_cli.py --auth",
            "status": "unauthenticated"
        }

    try:
        from tools.api_implementations.gmail_api import gmail_get_thread as gmail_get_thread_impl
        result = await gmail_get_thread_impl(creds, thread_id)
        logger.info(f"Retrieved Gmail thread: {thread_id}")
        return result
    except Exception as e:
        logger.error(f"gmail_get_thread failed: {e}")
        return {"error": str(e), "status": "error"}


async def gmail_send_message(
    to: str,
    subject: str,
    body: str,
    thread_id: Optional[str] = None,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    attachment_path: Optional[str] = None
) -> dict:
    """
    Send a Gmail message or reply to existing thread, with optional file attachment.

    IMPORTANT: 'to' must be a valid email address (user@domain.com).

    Args:
        to: Recipient email address (REQUIRED, must contain @)
        subject: Email subject line (REQUIRED)
        body: Email body content, can be plain text or HTML (REQUIRED)
        thread_id: Optional thread ID to reply to (makes this a reply)
        cc: Optional CC email addresses (comma-separated)
        bcc: Optional BCC email addresses (comma-separated)
        attachment_path: Optional local file path to attach (e.g., "output/invoices/invoice_1_1_1_abc.pdf")

    Returns:
        Dictionary containing:
            - id: Message ID
            - threadId: Thread ID
            - status: Success message

    Example:
        result = await gmail_send_message(
            to="recipient@example.com",
            subject="Fiskalizirani račun",
            body="U prilogu se nalazi fiskalizirani račun.",
            attachment_path="output/invoices/invoice_1_1_1_abc123.pdf"
        )
    """
    creds = _get_credentials()
    if creds is None:
        return {
            "error": "Authentication required. Run: python tools/oauth_cli.py --auth",
            "status": "unauthenticated"
        }

    # Validate email format
    if "@" not in to:
        return {
            "error": f"Invalid recipient email: '{to}'. Must be valid email address (user@domain.com)",
            "status": "invalid_email"
        }

    try:
        from tools.api_implementations.gmail_api import gmail_send_message as gmail_send_impl
        result = await gmail_send_impl(creds, to, subject, body, thread_id, cc, bcc, attachment_path)
        logger.info(f"Sent Gmail message to {to}: '{subject}'" + (f" with attachment: {attachment_path}" if attachment_path else ""))
        return result
    except Exception as e:
        logger.error(f"gmail_send_message failed: {e}")
        return {"error": str(e), "status": "error"}


async def gmail_create_draft(
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None
) -> dict:
    """
    Create a Gmail draft message without sending it.

    Use this for important emails that need review before sending.

    Args:
        to: Recipient email address (REQUIRED, must contain @)
        subject: Email subject line (REQUIRED)
        body: Email body content (REQUIRED)
        cc: Optional CC email addresses (comma-separated)

    Returns:
        Dictionary containing:
            - id: Draft ID
            - message: Draft message object
            - status: Success message
    """
    creds = _get_credentials()
    if creds is None:
        return {
            "error": "Authentication required. Run: python tools/oauth_cli.py --auth",
            "status": "unauthenticated"
        }

    # Validate email format
    if "@" not in to:
        return {
            "error": f"Invalid recipient email: '{to}'. Must be valid email address",
            "status": "invalid_email"
        }

    try:
        from tools.api_implementations.gmail_api import gmail_create_draft as gmail_create_draft_impl
        result = await gmail_create_draft_impl(creds, to, subject, body, cc)
        logger.info(f"Created Gmail draft to {to}: '{subject}'")
        return result
    except Exception as e:
        logger.error(f"gmail_create_draft failed: {e}")
        return {"error": str(e), "status": "error"}


async def gmail_modify_thread(
    thread_id: str,
    add_labels: Optional[List[str]] = None,
    remove_labels: Optional[List[str]] = None
) -> dict:
    """
    Modify labels on a Gmail thread.

    Use this to organize emails by adding or removing Gmail labels.

    Common system labels: INBOX, UNREAD, STARRED, IMPORTANT, SPAM, TRASH

    Args:
        thread_id: Gmail thread ID (REQUIRED)
        add_labels: List of label names to add (e.g., ['STARRED', 'IMPORTANT'])
        remove_labels: List of label names to remove (e.g., ['UNREAD', 'INBOX'])

    Returns:
        Dictionary containing:
            - id: Thread ID
            - labelIds: Updated list of labels
            - status: Success message
    """
    creds = _get_credentials()
    if creds is None:
        return {
            "error": "Authentication required. Run: python tools/oauth_cli.py --auth",
            "status": "unauthenticated"
        }

    try:
        from tools.api_implementations.gmail_api import gmail_modify_thread as gmail_modify_thread_impl
        result = await gmail_modify_thread_impl(creds, thread_id, add_labels, remove_labels)
        logger.info(f"Modified Gmail thread: {thread_id}")
        return result
    except Exception as e:
        logger.error(f"gmail_modify_thread failed: {e}")
        return {"error": str(e), "status": "error"}


async def gmail_list_labels() -> dict:
    """
    List all Gmail labels.

    Retrieves both system labels (INBOX, SENT, etc.) and user-created labels.

    Returns:
        Dictionary containing:
            - labels: List of label objects with id, name, type
            - count: Number of labels
    """
    creds = _get_credentials()
    if creds is None:
        return {
            "error": "Authentication required. Run: python tools/oauth_cli.py --auth",
            "status": "unauthenticated"
        }

    try:
        from tools.api_implementations.gmail_api import gmail_list_labels as gmail_list_labels_impl
        result = await gmail_list_labels_impl(creds)
        logger.info(f"Listed {result.get('count', 0)} Gmail labels")
        return result
    except Exception as e:
        logger.error(f"gmail_list_labels failed: {e}")
        return {"error": str(e), "status": "error"}
