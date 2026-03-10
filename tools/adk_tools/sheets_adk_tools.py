"""
Google Sheets ADK Tools

ADK-compatible wrapper for Google Sheets operations.
Converts existing Sheets API implementations to plain Python async functions
that ADK can auto-wrap as tools.

Tools:
- sheets_get_spreadsheet: Get metadata about a spreadsheet
- sheets_get_values: Read data from a range
- sheets_update_values: Write data to a range
- sheets_append_values: Append rows to end of sheet
- sheets_clear_values: Clear data from a range
- sheets_create_spreadsheet: Create new spreadsheet
- sheets_batch_update: Complex formatting and batch operations
- read_sheets_schema: Read column headers (schema-first approach)

Usage:
    from tools.adk_tools.sheets_adk_tools import get_sheets_adk_tools

    # Get all Sheets tools
    sheets_tools = get_sheets_adk_tools()

    # Create agent with Sheets tools
    agent = LlmAgent(
        name="analyst",
        model="gemini-2.5-flash",
        tools=sheets_tools
    )
"""

from typing import List, Dict, Any, Optional
from google.oauth2.credentials import Credentials
import logging
import os

logger = logging.getLogger(__name__)


# ============================================================================
# CREDENTIAL HELPER
# ============================================================================

def _get_credentials() -> Optional[Credentials]:
    """
    Get OAuth2 credentials from token file.

    Returns:
        Credentials object or None if not authenticated
    """
    try:
        from auth.credential_store import get_credential_store

        credential_store = get_credential_store()
        creds = credential_store.get_credentials()

        if creds is None:
            logger.warning("No credentials found. Use: python tools/oauth_cli.py --auth")
            return None

        return creds

    except Exception as e:
        logger.error(f"Failed to get credentials: {e}")
        return None


# ============================================================================
# ADK TOOL FUNCTIONS
# ============================================================================

async def sheets_get_spreadsheet(
    spreadsheet_id: str,
    include_grid_data: bool = False
) -> dict:
    """
    Get metadata and properties of a Google Sheets spreadsheet.

    Retrieves information about the spreadsheet including:
    - Title and URL
    - List of sheets (tabs) with names and IDs
    - Locale and timezone settings
    - Named ranges

    Args:
        spreadsheet_id: Google Sheets spreadsheet ID from URL
        include_grid_data: Include cell data (default: False). Set to True
            to get actual cell contents, but this uses more quota.

    Returns:
        Dictionary with spreadsheet metadata including sheets list, title,
        URL, locale, and timezone information

    Example:
        >>> metadata = await sheets_get_spreadsheet("1abc...")
        >>> print(metadata['title'])
        >>> for sheet in metadata['sheets']:
        ...     print(f"Sheet: {sheet['title']}")
    """
    creds = _get_credentials()
    if creds is None:
        return {
            "error": "Authentication required. Run: python tools/oauth_cli.py --auth",
            "status": "unauthenticated"
        }

    try:
        from tools.api_implementations.sheets_api import sheets_get_spreadsheet as sheets_get_impl
        result = await sheets_get_impl(creds, spreadsheet_id, include_grid_data)
        return result

    except Exception as e:
        logger.error(f"Error getting spreadsheet: {e}")
        return {
            "error": str(e),
            "status": "failed"
        }


async def sheets_get_values(
    spreadsheet_id: str,
    range: str,
    value_render_option: str = "FORMATTED_VALUE"
) -> dict:
    """
    Read data from a specific range in a Google Sheets spreadsheet.

    Retrieves cell values from the specified range using A1 notation.
    Returns a 2D array of values.

    Args:
        spreadsheet_id: Google Sheets spreadsheet ID from URL
        range: A1 notation range (e.g., 'Sheet1!A1:D10', 'Data!A:C').
            Can specify sheet name and range, or just range for first sheet.
        value_render_option: How values should be rendered:
            - "FORMATTED_VALUE" (default): Values as they appear in UI
            - "UNFORMATTED_VALUE": Raw values without formatting
            - "FORMULA": Show formulas instead of calculated values

    Returns:
        Dictionary with values array, row/column count, and range information

    Example:
        >>> data = await sheets_get_values("1abc...", "Sheet1!A1:C10")
        >>> values = data['values']  # 2D array
        >>> for row in values:
        ...     print(row)
    """
    creds = _get_credentials()
    if creds is None:
        return {
            "error": "Authentication required. Run: python tools/oauth_cli.py --auth",
            "status": "unauthenticated"
        }

    try:
        from tools.api_implementations.sheets_api import sheets_get_values as sheets_get_vals_impl
        result = await sheets_get_vals_impl(creds, spreadsheet_id, range, value_render_option)
        return result

    except Exception as e:
        logger.error(f"Error getting values: {e}")
        return {
            "error": str(e),
            "status": "failed"
        }


async def sheets_update_values(
    spreadsheet_id: str,
    range: str,
    values: List[List[str]],
    value_input_option: str = "USER_ENTERED"
) -> dict:
    """
    Write data to a specific range in a Google Sheets spreadsheet.

    Updates cell values in the specified range. The range will expand
    if the values array is larger than the specified range.

    Args:
        spreadsheet_id: Google Sheets spreadsheet ID from URL
        range: A1 notation range (e.g., 'Sheet1!A1:D10', 'Data!A1').
            Starting cell for the update.
        values: 2D array of values to write. Each inner list is a row.
            Example: [["Name", "Age"], ["Alice", "30"], ["Bob", "25"]]
        value_input_option: How input should be interpreted:
            - "USER_ENTERED" (default): Parses values as if typed in UI.
              Numbers and formulas are recognized automatically.
            - "RAW": Values stored as-is without parsing

    Returns:
        Dictionary with update result including updated cells count,
        updated range, and status

    Example:
        >>> result = await sheets_update_values(
        ...     "1abc...",
        ...     "Sheet1!A1",
        ...     [["Name", "Score"], ["Alice", "95"]]
        ... )
        >>> print(f"Updated {result['updated_cells']} cells")
    """
    creds = _get_credentials()
    if creds is None:
        return {
            "error": "Authentication required. Run: python tools/oauth_cli.py --auth",
            "status": "unauthenticated"
        }

    try:
        from tools.api_implementations.sheets_api import sheets_update_values as sheets_update_impl
        result = await sheets_update_impl(creds, spreadsheet_id, range, values, value_input_option)
        return result

    except Exception as e:
        logger.error(f"Error updating values: {e}")
        return {
            "error": str(e),
            "status": "failed"
        }


async def sheets_append_values(
    spreadsheet_id: str,
    range: str,
    values: List[List[str]],
    value_input_option: str = "USER_ENTERED"
) -> dict:
    """
    Append rows to the end of a sheet in a Google Sheets spreadsheet.

    Adds new rows after the last row with data in the specified range.
    Automatically finds the next empty row and inserts data there.

    Args:
        spreadsheet_id: Google Sheets spreadsheet ID from URL
        range: Sheet name or range (e.g., 'Sheet1', 'Data!A:Z').
            Specifies where to search for the table to append to.
        values: 2D array of values to append. Each inner list is a row.
            Example: [["Alice", "30", "Engineer"], ["Bob", "25", "Designer"]]
        value_input_option: How input should be interpreted:
            - "USER_ENTERED" (default): Parses values as if typed in UI
            - "RAW": Values stored as-is without parsing

    Returns:
        Dictionary with append result including table range, updated range,
        and number of rows/cells added

    Example:
        >>> result = await sheets_append_values(
        ...     "1abc...",
        ...     "Sheet1",
        ...     [["New Row", "Data"]]
        ... )
        >>> print(f"Appended {result['updated_rows']} rows")
    """
    creds = _get_credentials()
    if creds is None:
        return {
            "error": "Authentication required. Run: python tools/oauth_cli.py --auth",
            "status": "unauthenticated"
        }

    try:
        from tools.api_implementations.sheets_api import sheets_append_values as sheets_append_impl
        result = await sheets_append_impl(creds, spreadsheet_id, range, values, value_input_option)
        return result

    except Exception as e:
        logger.error(f"Error appending values: {e}")
        return {
            "error": str(e),
            "status": "failed"
        }


async def sheets_clear_values(
    spreadsheet_id: str,
    range: str
) -> dict:
    """
    Clear all values from a specific range in a Google Sheets spreadsheet.

    Removes cell contents but preserves formatting. Does not delete rows/columns.

    Args:
        spreadsheet_id: Google Sheets spreadsheet ID from URL
        range: A1 notation range to clear (e.g., 'Sheet1!A1:D10', 'Data!A:Z').
            All cells in this range will be cleared.

    Returns:
        Dictionary with clear result including cleared range and status

    Example:
        >>> result = await sheets_clear_values("1abc...", "Sheet1!A1:Z100")
        >>> print(f"Cleared range: {result['cleared_range']}")
    """
    creds = _get_credentials()
    if creds is None:
        return {
            "error": "Authentication required. Run: python tools/oauth_cli.py --auth",
            "status": "unauthenticated"
        }

    try:
        from tools.api_implementations.sheets_api import sheets_clear_values as sheets_clear_impl
        result = await sheets_clear_impl(creds, spreadsheet_id, range)
        return result

    except Exception as e:
        logger.error(f"Error clearing values: {e}")
        return {
            "error": str(e),
            "status": "failed"
        }


async def sheets_create_spreadsheet(
    title: str,
    sheet_titles: Optional[List[str]] = None
) -> dict:
    """
    Create a new Google Sheets spreadsheet.

    Creates a new spreadsheet in the user's Google Drive.
    Optionally specify custom sheet names instead of default "Sheet1".

    Args:
        title: Spreadsheet title (will appear in Google Drive)
        sheet_titles: Optional list of sheet names to create.
            If not provided, creates one sheet named "Sheet1".
            Example: ["Sales", "Expenses", "Summary"]

    Returns:
        Dictionary with created spreadsheet ID, URL, and sheets information

    Example:
        >>> result = await sheets_create_spreadsheet(
        ...     "Monthly Report",
        ...     ["Revenue", "Costs", "Profit"]
        ... )
        >>> print(f"Created: {result['spreadsheet_url']}")
        >>> spreadsheet_id = result['spreadsheet_id']
    """
    creds = _get_credentials()
    if creds is None:
        return {
            "error": "Authentication required. Run: python tools/oauth_cli.py --auth",
            "status": "unauthenticated"
        }

    try:
        from tools.api_implementations.sheets_api import sheets_create_spreadsheet as sheets_create_impl
        result = await sheets_create_impl(creds, title, sheet_titles)
        return result

    except Exception as e:
        logger.error(f"Error creating spreadsheet: {e}")
        return {
            "error": str(e),
            "status": "failed"
        }


async def sheets_batch_update(
    spreadsheet_id: str,
    requests: List[Dict[str, Any]]
) -> dict:
    """
    Perform complex batch updates on a Google Sheets spreadsheet.

    Execute multiple operations in a single API call. Supports:
    - Formatting (bold, colors, borders, number formats)
    - Adding/deleting sheets
    - Merging cells
    - Setting formulas
    - Conditional formatting
    - Data validation

    This is more efficient than multiple individual updates.

    Args:
        spreadsheet_id: Google Sheets spreadsheet ID from URL
        requests: List of request objects following Google Sheets API format.
            Each request is a dict with operation type and parameters.
            See Google Sheets API documentation for request formats.

    Returns:
        Dictionary with batch update results including replies for each
        request and updated spreadsheet information

    Example:
        >>> requests = [
        ...     {
        ...         "repeatCell": {
        ...             "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 1},
        ...             "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
        ...             "fields": "userEnteredFormat.textFormat.bold"
        ...         }
        ...     }
        ... ]
        >>> result = await sheets_batch_update("1abc...", requests)

    Note:
        This is an advanced operation. Refer to Google Sheets API documentation
        for request formats: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/request
    """
    creds = _get_credentials()
    if creds is None:
        return {
            "error": "Authentication required. Run: python tools/oauth_cli.py --auth",
            "status": "unauthenticated"
        }

    try:
        from tools.api_implementations.sheets_api import sheets_batch_update as sheets_batch_impl
        result = await sheets_batch_impl(creds, spreadsheet_id, requests)
        return result

    except Exception as e:
        logger.error(f"Error in batch update: {e}")
        return {
            "error": str(e),
            "status": "failed"
        }


async def read_sheets_schema(
    spreadsheet_id: str,
    sheet_name: str = "Sheet1"
) -> dict:
    """
    Read column headers (schema) from a Google Sheets spreadsheet.

    THIS IS A CRITICAL TOOL FOR EFFICIENT DATA READING!

    Schema-first approach: ALWAYS read the schema BEFORE reading data
    from large spreadsheets. This allows you to:
    1. Understand the data structure (column names)
    2. Ask user which columns they need
    3. Read only relevant columns (saves tokens/context)
    4. Avoid loading unnecessary data

    Reads the first row (header row) and returns column names with positions.

    Args:
        spreadsheet_id: Google Sheets spreadsheet ID from URL
        sheet_name: Sheet name to read schema from (default: "Sheet1")

    Returns:
        Dictionary with column names and their positions:
        {
            "columns": ["Date", "Product", "Revenue", "Region"],
            "column_count": 4,
            "column_mapping": {"Date": 0, "Product": 1, "Revenue": 2, "Region": 3},
            "status": "success"
        }

    Example Workflow:
        >>> # Step 1: Read schema first
        >>> schema = await read_sheets_schema("1abc...", "Sales")
        >>> print(schema['columns'])  # ["Date", "Product", "Revenue", "Region"]
        >>>
        >>> # Step 2: Ask user what to analyze
        >>> # "I see columns: Date, Product, Revenue, Region"
        >>> # "Which would you like to analyze?"
        >>>
        >>> # Step 3: Read only needed columns
        >>> data = await sheets_get_values("1abc...", "Sales!C:D")  # Only Revenue & Region

    Best Practice:
        For spreadsheets with >100 rows, ALWAYS:
        1. Read schema first with this tool
        2. Review column names
        3. Ask user which columns/metrics they need
        4. Read only those specific columns
    """
    creds = _get_credentials()
    if creds is None:
        return {
            "error": "Authentication required. Run: python tools/oauth_cli.py --auth",
            "status": "unauthenticated"
        }

    try:
        # Read first row (headers) using sheets_get_values
        from tools.api_implementations.sheets_api import sheets_get_values as sheets_get_vals_impl

        # A1 notation for first row with wide column range
        range_name = f"{sheet_name}!A1:ZZ1"

        result = await sheets_get_vals_impl(creds, spreadsheet_id, range_name, "FORMATTED_VALUE")

        headers = result.get('values', [[]])[0] if result.get('values') else []

        # Filter out empty headers and create mapping
        column_mapping = {}
        columns = []
        for idx, header in enumerate(headers):
            if header:  # Skip empty headers
                columns.append(header)
                column_mapping[header] = idx

        logger.info(f"Read schema with {len(columns)} columns from {sheet_name}")

        return {
            "columns": columns,
            "column_count": len(columns),
            "column_mapping": column_mapping,
            "sheet_name": sheet_name,
            "status": "success"
        }

    except Exception as e:
        logger.error(f"Error reading schema: {e}")
        return {
            "error": str(e),
            "status": "failed"
        }


# ============================================================================
# TOOL FACTORY
# ============================================================================

def get_sheets_adk_tools(credentials: Optional[Credentials] = None) -> list:
    """
    Get all Google Sheets ADK tools as a list.

    Returns plain Python async functions that ADK will automatically
    wrap as tools based on type hints and docstrings.

    Args:
        credentials: Optional OAuth2 credentials. If None, tools will
            fetch credentials from token file.

    Returns:
        List of 8 Sheets tool functions

    Tools included:
        1. sheets_get_spreadsheet - Get metadata
        2. sheets_get_values - Read data
        3. sheets_update_values - Write data
        4. sheets_append_values - Append rows
        5. sheets_clear_values - Clear data
        6. sheets_create_spreadsheet - Create spreadsheet
        7. sheets_batch_update - Complex formatting
        8. read_sheets_schema - Read headers (SCHEMA-FIRST!)

    Example:
        >>> from tools.adk_tools.sheets_adk_tools import get_sheets_adk_tools
        >>> from google.adk.agents import LlmAgent
        >>>
        >>> sheets_tools = get_sheets_adk_tools()
        >>> agent = LlmAgent(
        ...     name="analyst",
        ...     model="gemini-2.5-flash",
        ...     tools=sheets_tools
        ... )
    """
    tools = [
        sheets_get_spreadsheet,
        sheets_get_values,
        sheets_update_values,
        sheets_append_values,
        sheets_clear_values,
        sheets_create_spreadsheet,
        sheets_batch_update,
        read_sheets_schema,  # CRITICAL: Schema-first tool!
    ]

    logger.info(f"Created {len(tools)} Google Sheets ADK tools")
    return tools


# ============================================================================
# TOOL METADATA
# ============================================================================

def get_sheets_capabilities() -> dict:
    """
    Get capabilities summary for Sheets tools.

    Returns:
        Dictionary describing tool capabilities
    """
    return {
        "service": "Google Sheets",
        "tool_count": 8,
        "capabilities": [
            "Read spreadsheet metadata and structure",
            "Read data from ranges",
            "Write/update cell values",
            "Append rows to sheets",
            "Clear data from ranges",
            "Create new spreadsheets",
            "Complex batch updates and formatting",
            "Schema-first approach for efficient reading"
        ],
        "special_features": [
            "read_sheets_schema: CRITICAL for large spreadsheets",
            "A1 notation support for flexible range selection",
            "Automatic value parsing (formulas, numbers, dates)",
            "Batch operations for efficiency"
        ],
        "best_practices": [
            "ALWAYS read schema before reading large sheets",
            "Ask user which columns they need",
            "Read only relevant data to save context",
            "Use batch_update for multiple formatting operations"
        ]
    }


if __name__ == "__main__":
    # Test tool creation
    tools = get_sheets_adk_tools()
    print(f"[OK] Created {len(tools)} Sheets ADK tools")

    for tool in tools:
        print(f"  - {tool.__name__}: {tool.__doc__.split(chr(10))[0] if tool.__doc__ else 'No description'}")

    print("\nCapabilities:")
    caps = get_sheets_capabilities()
    for cap in caps['capabilities']:
        print(f"  - {cap}")

    print("\nSpecial Features:")
    for feat in caps['special_features']:
        print(f"  - {feat}")
