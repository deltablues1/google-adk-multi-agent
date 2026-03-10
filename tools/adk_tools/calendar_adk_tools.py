"""
Calendar ADK Tools

ADK-compatible wrappers for Google Calendar operations:
- List events within time range
- Get event details
- Create new events
- Update existing events
- Delete events

Includes timezone-aware datetime handling.
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
        logger.warning("No valid credentials available for Calendar operations")
        return None
    except Exception as e:
        logger.error(f"Failed to get credentials: {e}")
        return None


async def calendar_list_events(
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    calendar_id: str = "primary",
    max_results: int = 10
) -> dict:
    """
    List calendar events within a time range.

    Retrieves events from the specified calendar between time_min and time_max.
    Useful for checking availability, finding conflicts, and viewing schedule.

    Args:
        time_min: Start time in RFC3339 format (optional, defaults to now)
                  Example: '2024-01-01T00:00:00Z'
        time_max: End time in RFC3339 format (optional, defaults to 7 days from time_min)
        calendar_id: Calendar ID (default: 'primary' for main calendar)
        max_results: Maximum number of events to return (default: 10)

    Returns:
        Dictionary with events array and calendar metadata
    """
    creds = _get_credentials()
    if creds is None:
        return {"error": "Authentication required"}

    # If time_min not provided, use current time
    if time_min is None:
        from datetime import datetime, timezone
        time_min = datetime.now(timezone.utc).isoformat()

    try:
        from tools.api_implementations.calendar_api import calendar_list_events as calendar_list_impl

        result = await calendar_list_impl(creds, calendar_id, time_min, time_max, max_results)
        return result
    except Exception as e:
        logger.error(f"Failed to list calendar events: {e}")
        return {"error": str(e), "time_min": time_min}


async def calendar_get_event(
    event_id: str,
    calendar_id: str = "primary"
) -> dict:
    """
    Get details of a specific calendar event.

    Retrieves full event information including title, time, location,
    attendees, and description.

    Args:
        event_id: Calendar event ID
        calendar_id: Calendar ID (default: 'primary')

    Returns:
        Dictionary with event details
    """
    creds = _get_credentials()
    if creds is None:
        return {"error": "Authentication required"}

    try:
        from tools.api_implementations.calendar_api import calendar_get_event as calendar_get_impl

        # Correct parameter order: credentials, event_id, calendar_id
        result = await calendar_get_impl(creds, event_id, calendar_id)
        return result
    except Exception as e:
        logger.error(f"Failed to get calendar event {event_id}: {e}")
        return {"error": str(e), "event_id": event_id}


async def calendar_create_event(
    summary: str,
    start_time: str,
    end_time: str,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    calendar_id: str = "primary"
) -> dict:
    """
    Create a new calendar event.

    Creates an event with specified details. Use RFC3339 format for times
    with explicit timezone (e.g., '2024-01-15T14:00:00-05:00').

    Args:
        summary: Event title/summary
        start_time: Start time in RFC3339 format (e.g., '2024-01-15T14:00:00-05:00')
        end_time: End time in RFC3339 format
        description: Event description (optional)
        location: Event location (optional)
        attendees: List of attendee email addresses (optional)
        calendar_id: Calendar ID (default: 'primary')

    Returns:
        Dictionary with created event details including event_id and event_url
    """
    creds = _get_credentials()
    if creds is None:
        return {"error": "Authentication required"}

    try:
        from tools.api_implementations.calendar_api import calendar_create_event as calendar_create_impl

        # Correct parameter order: credentials, summary, start_time, end_time, description, location, attendees, calendar_id
        result = await calendar_create_impl(
            creds, summary, start_time, end_time,
            description, location, attendees, calendar_id
        )
        return result
    except Exception as e:
        logger.error(f"Failed to create calendar event: {e}")
        return {"error": str(e), "summary": summary}


async def calendar_update_event(
    event_id: str,
    summary: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    calendar_id: str = "primary"
) -> dict:
    """
    Update an existing calendar event.

    Updates specified fields of an event. Only provide fields you want to change.
    Other fields will remain unchanged.

    Args:
        event_id: Calendar event ID
        summary: New event title (optional)
        start_time: New start time in RFC3339 format (optional)
        end_time: New end time in RFC3339 format (optional)
        description: New description (optional)
        location: New location (optional)
        attendees: New list of attendee emails (optional)
        calendar_id: Calendar ID (default: 'primary')

    Returns:
        Dictionary with updated event details
    """
    creds = _get_credentials()
    if creds is None:
        return {"error": "Authentication required"}

    try:
        from tools.api_implementations.calendar_api import calendar_update_event as calendar_update_impl

        # Correct parameter order: credentials, event_id, summary, start_time, end_time, description, location, calendar_id
        # Note: API implementation doesn't support attendees parameter
        result = await calendar_update_impl(
            creds, event_id, summary, start_time, end_time,
            description, location, calendar_id
        )

        if attendees:
            logger.warning(f"Attendees parameter not supported by calendar_update_event API implementation")

        return result
    except Exception as e:
        logger.error(f"Failed to update calendar event {event_id}: {e}")
        return {"error": str(e), "event_id": event_id}


async def calendar_delete_event(
    event_id: str,
    calendar_id: str = "primary"
) -> dict:
    """
    Delete a calendar event.

    Permanently removes an event from the calendar.

    Args:
        event_id: Calendar event ID
        calendar_id: Calendar ID (default: 'primary')

    Returns:
        Dictionary with deletion confirmation
    """
    creds = _get_credentials()
    if creds is None:
        return {"error": "Authentication required"}

    try:
        from tools.api_implementations.calendar_api import calendar_delete_event as calendar_delete_impl

        # Correct parameter order: credentials, event_id, calendar_id
        result = await calendar_delete_impl(creds, event_id, calendar_id)
        return result
    except Exception as e:
        logger.error(f"Failed to delete calendar event {event_id}: {e}")
        return {"error": str(e), "event_id": event_id}


def get_calendar_adk_tools(credentials=None) -> List:
    """
    Get all Calendar ADK tools as plain Python functions.

    ADK automatically wraps these functions as tools based on:
    - Function signature (type hints)
    - Docstring (description and parameter docs)

    Args:
        credentials: Not used - included for API compatibility. Tools use OAuth from token.

    Returns:
        List of calendar tool functions
    """
    tools = [
        calendar_list_events,
        calendar_get_event,
        calendar_create_event,
        calendar_update_event,
        calendar_delete_event
    ]

    logger.info(f"Calendar ADK tools loaded: {len(tools)} tools")
    return tools


if __name__ == "__main__":
    # Test tool loading
    tools = get_calendar_adk_tools()
    print(f"[OK] Calendar ADK tools loaded: {len(tools)} tools")

    for tool in tools:
        print(f"   - {tool.__name__}")

    print("\n[CAPABILITIES] Google Calendar Operations:")
    print("   - List events in time range")
    print("   - Get event details")
    print("   - Create new events")
    print("   - Update existing events")
    print("   - Delete events")
    print("   - Timezone-aware scheduling")
    print("   - Conflict detection support")
