"""
Gmail API Implementation

Real Gmail API functions using Google Gmail API v1
"""

from typing import Dict, Any, List, Optional
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import logging

from tools.resilience.retry_handler import with_retry, RetryConfig
from tools.resilience.circuit_breaker import with_circuit_breaker
from tools.resilience.rate_limiter import with_rate_limit
from tools.resilience.cache import with_cache

logger = logging.getLogger(__name__)


# ============================================================================
# GMAIL API FUNCTIONS
# ============================================================================

@with_circuit_breaker("gmail")
@with_cache("gmail", ttl=60, user_id_param="credentials")  # Cache for 1 min (emails change frequently)
@with_rate_limit("gmail", user_id_param="credentials")
@with_retry(RetryConfig(max_retries=3, base_delay=1.0))
async def gmail_search_threads(
    credentials: Credentials,
    query: str,
    max_results: int = 10
) -> Dict[str, Any]:
    """
    Search Gmail threads using Gmail search query syntax

    Args:
        credentials: OAuth2 credentials
        query: Gmail search query (e.g., 'from:john@example.com', 'subject:meeting', 'is:unread')
        max_results: Maximum number of threads to return (default: 10)

    Returns:
        Dictionary with:
        - threads: List of thread objects with id, snippet
        - result_size_estimate: Total number of matching threads

    Raises:
        HttpError: If API call fails
    """
    try:
        from tools.google_api_client import GoogleAPIClient

        # Create API client
        api_client = GoogleAPIClient(credentials=credentials)
        service = api_client.gmail_service()

        # Search threads
        logger.info(f"Searching Gmail threads: query='{query}', max_results={max_results}")

        results = service.users().threads().list(
            userId='me',
            q=query,
            maxResults=max_results
        ).execute()

        threads = results.get('threads', [])
        result_size = results.get('resultSizeEstimate', 0)

        # Get thread details for each thread
        thread_details = []
        for thread in threads:
            thread_id = thread['id']
            thread_data = service.users().threads().get(
                userId='me',
                id=thread_id,
                format='metadata',
                metadataHeaders=['From', 'To', 'Subject', 'Date']
            ).execute()

            # Extract snippet and basic info
            messages = thread_data.get('messages', [])
            if messages:
                first_msg = messages[0]
                headers = {h['name']: h['value'] for h in first_msg.get('payload', {}).get('headers', [])}

                thread_details.append({
                    'id': thread_id,
                    'snippet': thread_data.get('snippet', ''),
                    'from': headers.get('From', ''),
                    'to': headers.get('To', ''),
                    'subject': headers.get('Subject', ''),
                    'date': headers.get('Date', ''),
                    'message_count': len(messages)
                })

        logger.info(f"Found {len(thread_details)} threads")

        return {
            'threads': thread_details,
            'result_size_estimate': result_size,
            'query': query
        }

    except HttpError as e:
        logger.error(f"Gmail search failed: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in gmail_search_threads: {e}")
        raise


@with_circuit_breaker("gmail")
@with_cache("gmail", ttl=60, user_id_param="credentials")  # Cache for 1 min
@with_rate_limit("gmail", user_id_param="credentials")
@with_retry(RetryConfig(max_retries=3, base_delay=1.0))
async def gmail_get_thread(
    credentials: Credentials,
    thread_id: str
) -> Dict[str, Any]:
    """
    Get full content of a Gmail thread by ID

    Args:
        credentials: OAuth2 credentials
        thread_id: Gmail thread ID

    Returns:
        Dictionary with thread details including all messages

    Raises:
        HttpError: If API call fails
    """
    try:
        from tools.google_api_client import GoogleAPIClient

        api_client = GoogleAPIClient(credentials=credentials)
        service = api_client.gmail_service()

        logger.info(f"Getting Gmail thread: {thread_id}")

        # Get full thread
        thread = service.users().threads().get(
            userId='me',
            id=thread_id,
            format='full'
        ).execute()

        # Parse messages
        messages = []
        for msg in thread.get('messages', []):
            headers = {h['name']: h['value'] for h in msg.get('payload', {}).get('headers', [])}

            # Extract body
            body = _extract_message_body(msg.get('payload', {}))

            messages.append({
                'id': msg['id'],
                'message_id': headers.get('Message-ID') or headers.get('Message-Id', ''),
                'from': headers.get('From', ''),
                'to': headers.get('To', ''),
                'subject': headers.get('Subject', ''),
                'date': headers.get('Date', ''),
                'body': body,
                'snippet': msg.get('snippet', '')
            })

        logger.info(f"Retrieved thread with {len(messages)} messages")

        return {
            'id': thread_id,
            'messages': messages,
            'message_count': len(messages)
        }

    except HttpError as e:
        logger.error(f"Failed to get Gmail thread: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in gmail_get_thread: {e}")
        raise


@with_circuit_breaker("gmail")
@with_rate_limit("gmail", cost=100, user_id_param="credentials")
@with_retry(RetryConfig(max_retries=3, base_delay=1.0))
async def gmail_send_message(
    credentials: Credentials,
    to: str,
    subject: str,
    body: str,
    thread_id: Optional[str] = None,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    attachment_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send a Gmail message with optional file attachment.

    Args:
        credentials: OAuth2 credentials
        to: Recipient email address
        subject: Email subject
        body: Email body (plain text or HTML)
        thread_id: Optional thread ID to reply to
        cc: Optional CC email addresses (comma-separated)
        bcc: Optional BCC email addresses (comma-separated)
        attachment_path: Optional local file path to attach (e.g., PDF invoice)

    Returns:
        Dictionary with sent message details

    Raises:
        HttpError: If API call fails
    """
    try:
        from tools.google_api_client import GoogleAPIClient

        api_client = GoogleAPIClient(credentials=credentials)
        service = api_client.gmail_service()

        logger.info(f"Sending Gmail message: to={to}, subject='{subject}'")

        # If replying to a thread, fetch the last message's Message-ID for proper threading
        original_message_id = None
        references = None
        if thread_id:
            try:
                thread_data = service.users().threads().get(
                    userId='me',
                    id=thread_id,
                    format='metadata',
                    metadataHeaders=['Message-ID', 'References', 'Subject']
                ).execute()
                thread_messages = thread_data.get('messages', [])
                if thread_messages:
                    last_msg = thread_messages[-1]
                    headers = {h['name']: h['value'] for h in last_msg.get('payload', {}).get('headers', [])}
                    original_message_id = headers.get('Message-ID') or headers.get('Message-Id')
                    references = headers.get('References', '')
                    # Use original subject with Re: prefix if not already present
                    original_subject = headers.get('Subject', '')
                    if original_subject and not subject.lower().startswith('re:'):
                        subject = f"Re: {original_subject}"
                    logger.info(f"Reply threading: In-Reply-To={original_message_id}")
            except Exception as e:
                logger.warning(f"Could not fetch thread headers for reply threading: {e}")

        # Create message
        message = MIMEMultipart()
        message['to'] = to
        message['subject'] = subject

        # Set threading headers for proper reply display
        if original_message_id:
            message['In-Reply-To'] = original_message_id
            if references:
                message['References'] = f"{references} {original_message_id}"
            else:
                message['References'] = original_message_id

        if cc:
            message['cc'] = cc
        if bcc:
            message['bcc'] = bcc

        # Add body
        msg_body = MIMEText(body, 'plain')
        message.attach(msg_body)

        # Add attachment if provided
        if attachment_path:
            import os
            # Resolve relative paths from project root
            if not os.path.isabs(attachment_path):
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                attachment_path = os.path.join(project_root, attachment_path)

            if os.path.exists(attachment_path):
                filename = os.path.basename(attachment_path)
                ext = os.path.splitext(filename)[1].lower()
                subtype_map = {'.pdf': 'pdf', '.xlsx': 'vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                               '.docx': 'vnd.openxmlformats-officedocument.wordprocessingml.document',
                               '.png': 'png', '.jpg': 'jpeg', '.jpeg': 'jpeg'}
                subtype = subtype_map.get(ext, 'octet-stream')

                with open(attachment_path, 'rb') as f:
                    file_attachment = MIMEApplication(f.read(), _subtype=subtype)
                file_attachment.add_header('Content-Disposition', 'attachment', filename=filename)
                message.attach(file_attachment)
                logger.info(f"Attached file: {filename} ({os.path.getsize(attachment_path)} bytes)")
            else:
                logger.warning(f"Attachment file not found: {attachment_path}")

        # Encode message
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

        # Prepare send request
        send_request = {'raw': raw_message}

        # If replying to a thread, add threadId
        if thread_id:
            send_request['threadId'] = thread_id
            logger.info(f"Replying to thread: {thread_id}")

        # Send message
        sent_message = service.users().messages().send(
            userId='me',
            body=send_request
        ).execute()

        logger.info(f"Message sent successfully: id={sent_message['id']}")

        return {
            'id': sent_message['id'],
            'thread_id': sent_message.get('threadId'),
            'label_ids': sent_message.get('labelIds', []),
            'status': 'sent'
        }

    except HttpError as e:
        logger.error(f"Failed to send Gmail message: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in gmail_send_message: {e}")
        raise


@with_circuit_breaker("gmail")
@with_rate_limit("gmail", cost=50, user_id_param="credentials")
@with_retry(RetryConfig(max_retries=3, base_delay=1.0))
async def gmail_create_draft(
    credentials: Credentials,
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a Gmail draft message without sending

    Args:
        credentials: OAuth2 credentials
        to: Recipient email address
        subject: Email subject
        body: Email body (plain text or HTML)
        cc: Optional CC email addresses (comma-separated)

    Returns:
        Dictionary with draft details

    Raises:
        HttpError: If API call fails
    """
    try:
        from tools.google_api_client import GoogleAPIClient

        api_client = GoogleAPIClient(credentials=credentials)
        service = api_client.gmail_service()

        logger.info(f"Creating Gmail draft: to={to}, subject='{subject}'")

        # Create message
        message = MIMEMultipart()
        message['to'] = to
        message['subject'] = subject

        if cc:
            message['cc'] = cc

        # Add body
        msg_body = MIMEText(body, 'plain')
        message.attach(msg_body)

        # Encode message
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

        # Create draft
        draft = service.users().drafts().create(
            userId='me',
            body={'message': {'raw': raw_message}}
        ).execute()

        logger.info(f"Draft created successfully: id={draft['id']}")

        return {
            'id': draft['id'],
            'message_id': draft['message']['id'],
            'status': 'draft'
        }

    except HttpError as e:
        logger.error(f"Failed to create Gmail draft: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in gmail_create_draft: {e}")
        raise


@with_circuit_breaker("gmail")
@with_rate_limit("gmail", user_id_param="credentials")
@with_retry(RetryConfig(max_retries=3, base_delay=1.0))
async def gmail_modify_thread(
    credentials: Credentials,
    thread_id: str,
    add_labels: Optional[List[str]] = None,
    remove_labels: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Modify labels on a Gmail thread

    Args:
        credentials: OAuth2 credentials
        thread_id: Gmail thread ID
        add_labels: Labels to add (e.g., ['STARRED', 'IMPORTANT'])
        remove_labels: Labels to remove (e.g., ['UNREAD', 'INBOX'])

    Returns:
        Dictionary with modified thread details

    Raises:
        HttpError: If API call fails
    """
    try:
        from tools.google_api_client import GoogleAPIClient

        api_client = GoogleAPIClient(credentials=credentials)
        service = api_client.gmail_service()

        logger.info(f"Modifying Gmail thread: {thread_id}")

        # Prepare modification request
        modify_request = {}
        if add_labels:
            modify_request['addLabelIds'] = add_labels
            logger.info(f"Adding labels: {add_labels}")
        if remove_labels:
            modify_request['removeLabelIds'] = remove_labels
            logger.info(f"Removing labels: {remove_labels}")

        # Modify thread
        modified_thread = service.users().threads().modify(
            userId='me',
            id=thread_id,
            body=modify_request
        ).execute()

        logger.info(f"Thread modified successfully: {thread_id}")

        return {
            'id': modified_thread['id'],
            'label_ids': modified_thread.get('messages', [{}])[0].get('labelIds', []),
            'status': 'modified'
        }

    except HttpError as e:
        logger.error(f"Failed to modify Gmail thread: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in gmail_modify_thread: {e}")
        raise


@with_circuit_breaker("gmail")
@with_cache("gmail", ttl=900, user_id_param="credentials")  # Cache for 15 min (labels rarely change)
@with_rate_limit("gmail", user_id_param="credentials")
@with_retry(RetryConfig(max_retries=3, base_delay=1.0))
async def gmail_list_labels(
    credentials: Credentials
) -> Dict[str, Any]:
    """
    List all Gmail labels (system and user-created)

    Args:
        credentials: OAuth2 credentials

    Returns:
        Dictionary with list of labels

    Raises:
        HttpError: If API call fails
    """
    try:
        from tools.google_api_client import GoogleAPIClient

        api_client = GoogleAPIClient(credentials=credentials)
        service = api_client.gmail_service()

        logger.info("Listing Gmail labels")

        # Get labels
        results = service.users().labels().list(userId='me').execute()
        labels = results.get('labels', [])

        # Organize labels by type
        system_labels = []
        user_labels = []

        for label in labels:
            label_data = {
                'id': label['id'],
                'name': label['name'],
                'type': label.get('type', 'user')
            }

            if label.get('type') == 'system':
                system_labels.append(label_data)
            else:
                user_labels.append(label_data)

        logger.info(f"Found {len(labels)} labels ({len(system_labels)} system, {len(user_labels)} user)")

        return {
            'labels': labels,
            'system_labels': system_labels,
            'user_labels': user_labels,
            'total_count': len(labels)
        }

    except HttpError as e:
        logger.error(f"Failed to list Gmail labels: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in gmail_list_labels: {e}")
        raise


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _extract_message_body(payload: Dict[str, Any]) -> str:
    """
    Extract message body from Gmail message payload

    Args:
        payload: Gmail message payload

    Returns:
        Decoded message body
    """
    body = ""

    if 'body' in payload and 'data' in payload['body']:
        body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
    elif 'parts' in payload:
        for part in payload['parts']:
            if part.get('mimeType') == 'text/plain':
                if 'data' in part.get('body', {}):
                    body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                    break

    return body


# ============================================================================
# TOOL REGISTRATION
# ============================================================================

def register_gmail_tools(tool_registry):
    """
    Register all Gmail tools in the tool registry

    Args:
        tool_registry: ToolRegistry instance
    """
    # gmail_search_threads
    tool_registry.register_tool(
        name="gmail_search_threads",
        function=gmail_search_threads,
        description="Search Gmail threads using Gmail search query syntax. Returns list of thread IDs and snippets.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Gmail search query (e.g., 'from:john@example.com', 'subject:meeting', 'is:unread')"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of threads to return (default: 10)",
                    "default": 10
                }
            },
            "required": ["query"]
        },
        requires_auth=True,
        auth_type="oauth"
    )

    # gmail_get_thread
    tool_registry.register_tool(
        name="gmail_get_thread",
        function=gmail_get_thread,
        description="Get full content of a Gmail thread by ID, including all messages in the thread.",
        parameters={
            "type": "object",
            "properties": {
                "thread_id": {
                    "type": "string",
                    "description": "Gmail thread ID"
                }
            },
            "required": ["thread_id"]
        },
        requires_auth=True,
        auth_type="oauth"
    )

    # gmail_send_message
    tool_registry.register_tool(
        name="gmail_send_message",
        function=gmail_send_message,
        description="Send a new Gmail message. Can be a reply to an existing thread or a new conversation.",
        parameters={
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body (plain text or HTML)"},
                "thread_id": {"type": "string", "description": "Optional: Thread ID to reply to"},
                "cc": {"type": "string", "description": "Optional: CC email addresses (comma-separated)"},
                "bcc": {"type": "string", "description": "Optional: BCC email addresses (comma-separated)"}
            },
            "required": ["to", "subject", "body"]
        },
        requires_auth=True,
        auth_type="oauth"
    )

    # gmail_create_draft
    tool_registry.register_tool(
        name="gmail_create_draft",
        function=gmail_create_draft,
        description="Create a Gmail draft message without sending it.",
        parameters={
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body (plain text or HTML)"},
                "cc": {"type": "string", "description": "Optional: CC email addresses (comma-separated)"}
            },
            "required": ["to", "subject", "body"]
        },
        requires_auth=True,
        auth_type="oauth"
    )

    # gmail_modify_thread
    tool_registry.register_tool(
        name="gmail_modify_thread",
        function=gmail_modify_thread,
        description="Modify labels on a Gmail thread (add/remove labels like INBOX, UNREAD, STARRED, etc.)",
        parameters={
            "type": "object",
            "properties": {
                "thread_id": {"type": "string", "description": "Gmail thread ID"},
                "add_labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Labels to add (e.g., ['STARRED', 'IMPORTANT'])"
                },
                "remove_labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Labels to remove (e.g., ['UNREAD', 'INBOX'])"
                }
            },
            "required": ["thread_id"]
        },
        requires_auth=True,
        auth_type="oauth"
    )

    # gmail_list_labels
    tool_registry.register_tool(
        name="gmail_list_labels",
        function=gmail_list_labels,
        description="List all Gmail labels (both system and user-created labels).",
        parameters={
            "type": "object",
            "properties": {}
        },
        requires_auth=True,
        auth_type="oauth"
    )

    logger.info("Gmail tools registered successfully")
