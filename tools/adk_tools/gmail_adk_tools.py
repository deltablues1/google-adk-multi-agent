"""
Gmail ADK Tools

ADK-compatible wrappers for Gmail operations.
"""

from typing import Optional, List
import re
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
# RECIPIENT-SCOPED DOC SHARING (least privilege)
# ============================================================================
# When an outgoing email links a Google Doc/Drive file, the recipient must be
# able to open it. Rather than making the document public ("anyone with link"),
# we share it directly with the actual recipient(s) at send time. This is
# deterministic (runs in code, not at the LLM's discretion) and least-privilege.

# Capture the file ID from the common Google Docs/Sheets/Slides/Drive link forms.
_DRIVE_LINK_PATTERNS = [
    re.compile(r"https?://docs\.google\.com/(?:document|spreadsheets|presentation)/d/([a-zA-Z0-9_-]+)"),
    re.compile(r"https?://drive\.google\.com/file/d/([a-zA-Z0-9_-]+)"),
    re.compile(r"https?://drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)"),
]


def _extract_drive_file_ids(text: str) -> List[str]:
    """Return de-duplicated Google Drive/Docs file IDs linked in *text*."""
    ids: List[str] = []
    if not text:
        return ids
    for pattern in _DRIVE_LINK_PATTERNS:
        for fid in pattern.findall(text):
            if fid not in ids:
                ids.append(fid)
    return ids


def _parse_recipients(*fields: Optional[str]) -> List[str]:
    """Flatten comma/semicolon-separated to/cc fields into unique email addresses."""
    emails: List[str] = []
    for field in fields:
        if not field:
            continue
        for part in str(field).replace(";", ",").split(","):
            addr = part.strip()
            if "@" in addr and addr not in emails:
                emails.append(addr)
    return emails


async def _autoshare_linked_docs(creds, body: str, recipients: List[str]) -> List[str]:
    """Share any Google Doc/Drive file linked in *body* with *recipients* (reader).

    Best-effort: failures never block the send, but they are returned as
    warnings so the caller can tell the user a linked doc may not open.
    Only files owned/shareable by the sending account will actually share.
    """
    warnings: List[str] = []
    file_ids = _extract_drive_file_ids(body)
    if not file_ids or not recipients:
        return warnings
    try:
        from tools.api_implementations.drive_api import drive_share_file as drive_share_impl
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"[autoshare] drive_api import failed: {e}")
        return [f"Could not share linked documents (drive_api unavailable: {e})"]
    for fid in file_ids:
        for email in recipients:
            try:
                # send_notification=False: we are about to email the recipient
                # ourselves, so suppress Drive's duplicate "shared with you" mail.
                await drive_share_impl(creds, fid, email, "reader", "user", send_notification=False)
                logger.info(f"[autoshare] shared {fid} with {email} (reader, no notify)")
            except Exception as e:
                logger.warning(f"[autoshare] could not share {fid} with {email}: {e}")
                warnings.append(
                    f"Linked document {fid} could not be shared with {email} — "
                    "the recipient may get 'access denied' when opening the link."
                )
    return warnings


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

    # Validate the attachment BEFORE auto-sharing linked docs: a send that is
    # doomed to fail must not leave documents shared with the recipients.
    if attachment_path:
        from tools.api_implementations.gmail_api import validate_attachment_path

        _, path_error = validate_attachment_path(attachment_path)
        if path_error:
            return {"error": path_error, "status": "failed"}

    # Least-privilege: share any linked Google Doc/Drive file with the actual
    # recipients before sending, so the emailed link opens (no public sharing).
    share_warnings = await _autoshare_linked_docs(
        creds, body, _parse_recipients(to, cc, bcc)
    )

    try:
        from tools.api_implementations.gmail_api import gmail_send_message as gmail_send_impl
        result = await gmail_send_impl(creds, to, subject, body, thread_id, cc, bcc, attachment_path)
        logger.info(f"Sent Gmail message to {to}: '{subject}'" + (f" with attachment: {attachment_path}" if attachment_path else ""))
        if share_warnings and isinstance(result, dict):
            result["share_warning"] = " ".join(share_warnings)
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

    # Deliberately NO doc auto-sharing here: a draft may never be sent, and
    # sharing at draft time would leak access prematurely. Linked docs are
    # shared at send time (gmail_send_message); drafts sent manually from the
    # Gmail UI need manual sharing.
    try:
        from tools.api_implementations.gmail_api import gmail_create_draft as gmail_create_draft_impl
        result = await gmail_create_draft_impl(creds, to, subject, body, cc)
        logger.info(f"Created Gmail draft to {to}: '{subject}'")
        if isinstance(result, dict) and _extract_drive_file_ids(body):
            result["share_note"] = (
                "Draft contains Drive/Docs links. They are NOT shared yet — "
                "sharing happens automatically only when sending via this "
                "system. If the user sends the draft manually from Gmail, "
                "the documents must be shared manually."
            )
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
