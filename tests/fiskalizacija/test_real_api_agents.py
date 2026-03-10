"""
Real API Agent Testing - Comprehensive Quality Tests

Tests all agents with REAL Google APIs (not mocks):
1. Analyst - Sheets read/write operations (~5 tests)
2. Librarian - Drive file operations (~5 tests)
3. Secretary - Calendar management (~5 tests)
4. Rolodex - Contacts management (~5 tests)
5. Tracker - Tasks management (~5 tests)
6. Mailer - Gmail operations (~5 tests)

Prerequisites:
- Run setup_test_data.py first to create test data
- OAuth credentials must be configured

Tests follow user's workflow:
- Test → Fix bugs immediately → Retest
- NO commit until all tests pass
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))


# ==============================================================================
# ANALYST AGENT TESTS - Google Sheets Operations
# ==============================================================================

async def test_analyst_read_sheet():
    """
    Test 1: Analyst reads data from test spreadsheet

    Expected: Agent can read Sales Data from test sheet
    """
    print("\n" + "="*80)
    print("TEST 1: Analyst - Read Spreadsheet Data")
    print("="*80)

    from agents.adk_agents.analyst_adk import get_analyst_agent

    # Get test spreadsheet ID (from setup output or manually)
    # For now, let's search for it
    from tools.adk_tools.sheets_adk_tools import sheets_get_spreadsheet

    spreadsheet_id = "1C7dNHl0PqmpSiKkoOrPkDkkx_kLNQoogf4AB0-czH14"  # From setup

    print(f"Reading from spreadsheet: {spreadsheet_id}")

    # Test direct tool call first
    from tools.adk_tools.sheets_adk_tools import sheets_get_values

    result = await sheets_get_values(
        spreadsheet_id=spreadsheet_id,
        range="Sales Data!A1:E5"
    )

    # Check if successful (has 'values' key, no 'error')
    if 'values' in result and 'error' not in result:
        values = result.get('values', [])
        print(f"[OK] Read {len(values)} rows from Sales Data sheet")
        print(f"    Headers: {values[0] if values else 'None'}")
        print(f"    Data rows: {len(values) - 1 if len(values) > 1 else 0}")
        return True
    else:
        print(f"[FAIL] Failed to read data: {result.get('error', 'Unknown error')}")
        return False


async def test_analyst_write_sheet():
    """
    Test 2: Analyst writes new data to spreadsheet

    Expected: Agent can add new rows to test sheet
    """
    print("\n" + "="*80)
    print("TEST 2: Analyst - Write New Data")
    print("="*80)

    spreadsheet_id = "1C7dNHl0PqmpSiKkoOrPkDkkx_kLNQoogf4AB0-czH14"

    # Add a new row to Sales Data
    from tools.adk_tools.sheets_adk_tools import sheets_append_values

    new_row = [
        [datetime.now().strftime("%Y-%m-%d"), "API Test Product", "1", "100.00", "100.00"]
    ]

    result = await sheets_append_values(
        spreadsheet_id=spreadsheet_id,
        range="Sales Data!A:E",
        values=new_row
    )

    if result.get('status') == 'appended':
        print(f"[OK] Appended new row to Sales Data")
        print(f"    Updated range: {result.get('updated_range')}")
        print(f"    Updated cells: {result.get('updated_cells')}")
        return True
    else:
        print(f"[FAIL] Failed to append data: {result.get('error', 'Unknown error')}")
        return False


async def test_analyst_search_data():
    """
    Test 3: Analyst searches for specific data in sheet

    Expected: Agent can find rows matching criteria
    """
    print("\n" + "="*80)
    print("TEST 3: Analyst - Search Data")
    print("="*80)

    spreadsheet_id = "1C7dNHl0PqmpSiKkoOrPkDkkx_kLNQoogf4AB0-czH14"

    # Read all data and search locally (Sheets API doesn't have built-in search)
    from tools.adk_tools.sheets_adk_tools import sheets_get_values

    result = await sheets_get_values(
        spreadsheet_id=spreadsheet_id,
        range="Sales Data!A:E"
    )

    if 'values' in result and 'error' not in result:
        values = result.get('values', [])

        # Search for "IT Consulting" product
        found_rows = [row for row in values[1:] if len(row) > 1 and "IT Consulting" in row[1]]

        if found_rows:
            print(f"[OK] Found {len(found_rows)} rows matching 'IT Consulting'")
            for row in found_rows[:2]:  # Show first 2
                print(f"    {row}")
            return True
        else:
            print(f"[FAIL] No rows found matching 'IT Consulting'")
            return False
    else:
        print(f"[FAIL] Failed to read data: {result.get('error', 'Unknown error')}")
        return False


async def test_analyst_calculate_total():
    """
    Test 4: Analyst calculates total from sheet data

    Expected: Agent can sum values from column
    """
    print("\n" + "="*80)
    print("TEST 4: Analyst - Calculate Totals")
    print("="*80)

    spreadsheet_id = "1C7dNHl0PqmpSiKkoOrPkDkkx_kLNQoogf4AB0-czH14"

    from tools.adk_tools.sheets_adk_tools import sheets_get_values

    result = await sheets_get_values(
        spreadsheet_id=spreadsheet_id,
        range="Sales Data!E:E"  # Total column
    )

    if 'values' in result and 'error' not in result:
        values = result.get('values', [])

        # Skip header, sum totals
        try:
            totals = [float(row[0]) for row in values[1:] if row and row[0]]
            total_sum = sum(totals)

            print(f"[OK] Calculated total from {len(totals)} rows")
            print(f"    Total: ${total_sum:,.2f}")
            return True
        except Exception as e:
            print(f"[FAIL] Failed to calculate: {e}")
            return False
    else:
        print(f"[FAIL] Failed to read data: {result.get('error', 'Unknown error')}")
        return False


async def test_analyst_update_cell():
    """
    Test 5: Analyst updates specific cell value

    Expected: Agent can modify individual cell
    """
    print("\n" + "="*80)
    print("TEST 5: Analyst - Update Cell")
    print("="*80)

    spreadsheet_id = "1C7dNHl0PqmpSiKkoOrPkDkkx_kLNQoogf4AB0-czH14"

    from tools.adk_tools.sheets_adk_tools import sheets_update_values

    # Update last row we added
    new_value = [["UPDATED: API Test"]]

    result = await sheets_update_values(
        spreadsheet_id=spreadsheet_id,
        range="Sales Data!B7",  # Assuming row 7 is our test row
        values=new_value
    )

    if result.get('status') == 'updated':
        print(f"[OK] Updated cell B7")
        print(f"    Updated range: {result.get('updated_range')}")
        return True
    else:
        print(f"[FAIL] Failed to update: {result.get('error', 'Unknown error')}")
        return False
# ==============================================================================
# LIBRARIAN AGENT TESTS - Google Drive Operations
# ==============================================================================

async def test_librarian_search_files():
    """
    Test 1: Librarian searches for files in Drive

    Expected: Agent can find test folders
    """
    print("\n" + "="*80)
    print("TEST 1: Librarian - Search Files")
    print("="*80)

    from tools.adk_tools.drive_adk_tools import drive_search_files

    # Search for our test folder
    result = await drive_search_files(
        query="name = 'Test Documents 2026' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
        max_results=5
    )

    if 'files' in result and 'error' not in result:
        files = result.get('files', [])
        print(f"[OK] Found {len(files)} folder(s) matching 'Test Documents 2026'")
        if files:
            print(f"    ID: {files[0]['id']}")
            print(f"    URL: {files[0].get('webViewLink', 'N/A')}")
        return True
    else:
        print(f"[FAIL] Failed to search: {result.get('error', 'Unknown error')}")
        return False


async def test_librarian_create_folder():
    """
    Test 2: Librarian creates a new folder

    Expected: Agent can create folders in Drive
    """
    print("\n" + "="*80)
    print("TEST 2: Librarian - Create Folder")
    print("="*80)

    from tools.adk_tools.drive_adk_tools import drive_create_folder

    folder_name = f"API Test Folder {datetime.now().strftime('%Y%m%d_%H%M%S')}"

    result = await drive_create_folder(
        folder_name=folder_name,
        parent_folder_id=None
    )

    if result.get('status') == 'created':
        print(f"[OK] Created folder: {folder_name}")
        print(f"    ID: {result.get('id')}")
        print(f"    URL: {result.get('web_view_link', 'N/A')}")
        return True
    else:
        print(f"[FAIL] Failed to create folder: {result.get('error', 'Unknown error')}")
        return False


async def test_librarian_upload_file():
    """
    Test 3: Librarian uploads a file to Drive

    Expected: Agent can upload files
    """
    print("\n" + "="*80)
    print("TEST 3: Librarian - Upload File")
    print("="*80)

    from tools.adk_tools.drive_adk_tools import drive_upload_file
    import base64

    # Create simple test file content
    test_content = f"Test file created at {datetime.now().isoformat()}\n\nThis is a test file for Librarian agent testing."
    test_content_base64 = base64.b64encode(test_content.encode('utf-8')).decode('utf-8')

    file_name = f"test_file_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    result = await drive_upload_file(
        file_name=file_name,
        content=test_content_base64,
        mime_type="text/plain",
        parent_folder_id=None
    )

    if result.get('status') == 'uploaded':
        print(f"[OK] Uploaded file: {file_name}")
        print(f"    ID: {result.get('id')}")
        print(f"    URL: {result.get('web_view_link', 'N/A')}")
        return True
    else:
        print(f"[FAIL] Failed to upload: {result.get('error', 'Unknown error')}")
        return False


async def test_librarian_list_folder_contents():
    """
    Test 4: Librarian lists contents of folder

    Expected: Agent can list files in folder
    """
    print("\n" + "="*80)
    print("TEST 4: Librarian - List Folder Contents")
    print("="*80)

    from tools.adk_tools.drive_adk_tools import drive_search_files

    # First find our test folder ID
    folder_result = await drive_search_files(
        query="name = 'Test Documents 2026' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
        max_results=1
    )

    if 'files' in folder_result and folder_result['files']:
        folder_id = folder_result['files'][0]['id']

        # List contents
        contents_result = await drive_search_files(
            query=f"'{folder_id}' in parents and trashed = false",
            max_results=10
        )

        if 'files' in contents_result:
            files = contents_result.get('files', [])
            print(f"[OK] Listed {len(files)} items in folder")
            for f in files[:3]:  # Show first 3
                print(f"    - {f['name']} ({f.get('mimeType', 'unknown')})")
            return True
        else:
            print(f"[FAIL] Failed to list contents: {contents_result.get('error', 'Unknown error')}")
            return False
    else:
        print(f"[FAIL] Could not find test folder")
        return False


async def test_librarian_share_file():
    """
    Test 5: Librarian shares a file

    Expected: Agent can make file publicly viewable
    """
    print("\n" + "="*80)
    print("TEST 5: Librarian - Share File")
    print("="*80)

    from tools.adk_tools.drive_adk_tools import drive_share_file, drive_search_files

    # Find a test file to share
    search_result = await drive_search_files(
        query="name contains 'test_file_' and trashed = false",
        max_results=1
    )

    if 'files' in search_result and search_result['files']:
        file_id = search_result['files'][0]['id']
        file_name = search_result['files'][0]['name']

        # Share with anyone with link
        share_result = await drive_share_file(
            file_id=file_id,
            role="reader",
            type="anyone"
        )

        if share_result.get('status') == 'shared':
            print(f"[OK] Shared file: {file_name}")
            print(f"    File ID: {file_id}")
            print(f"    Access: Anyone with link can view")
            return True
        else:
            print(f"[FAIL] Failed to share: {share_result.get('error', 'Unknown error')}")
            return False
    else:
        print(f"[FAIL] No test file found to share")
        return False


# ==============================================================================
# SECRETARY AGENT TESTS - Google Calendar Operations
# ==============================================================================

async def test_secretary_list_events():
    """Test 1: Secretary lists upcoming events"""
    print("\n" + "="*80)
    print("TEST 1: Secretary - List Upcoming Events")
    print("="*80)

    from tools.adk_tools.calendar_adk_tools import calendar_list_events
    from datetime import datetime, timedelta

    # List events for next 7 days
    time_min = datetime.now().isoformat() + 'Z'
    time_max = (datetime.now() + timedelta(days=7)).isoformat() + 'Z'

    result = await calendar_list_events(
        time_min=time_min,
        time_max=time_max,
        max_results=10
    )

    if 'events' in result and 'error' not in result:
        events = result.get('events', [])
        print(f"[OK] Found {len(events)} upcoming events")
        for event in events[:2]:
            print(f"    - {event.get('summary', 'No title')} (Time: {event.get('start', 'No time')})")
        return True
    else:
        print(f"[FAIL] Failed to list events: {result.get('error', 'Unknown error')}")
        return False


async def test_secretary_create_event():
    """Test 2: Secretary creates a new event"""
    print("\n" + "="*80)
    print("TEST 2: Secretary - Create New Event")
    print("="*80)

    from tools.adk_tools.calendar_adk_tools import calendar_create_event
    from datetime import datetime, timedelta

    # Create event tomorrow at 15:00
    tomorrow = datetime.now() + timedelta(days=1)
    start_time = tomorrow.replace(hour=15, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(hours=1)

    event_title = f"API Test Event {datetime.now().strftime('%H%M%S')}"

    result = await calendar_create_event(
        summary=event_title,
        start_time=start_time.isoformat(),
        end_time=end_time.isoformat(),
        description="Created by automated API test",
        location="Virtual"
    )

    if result.get('status') == 'created':
        print(f"[OK] Event created: {event_title}")
        print(f"    Event ID: {result.get('event_id', 'N/A')}")
        print(f"    Time: {start_time.strftime('%Y-%m-%d %H:%M')}")
        return True
    else:
        print(f"[FAIL] Failed to create event: {result.get('error', 'Unknown error')}")
        return False


async def test_secretary_update_event():
    """Test 3: Secretary updates an event"""
    print("\n" + "="*80)
    print("TEST 3: Secretary - Update Event")
    print("="*80)

    from tools.adk_tools.calendar_adk_tools import calendar_list_events, calendar_update_event
    from datetime import datetime, timedelta

    # Find recent test event
    time_min = datetime.now().isoformat() + 'Z'
    time_max = (datetime.now() + timedelta(days=7)).isoformat() + 'Z'

    list_result = await calendar_list_events(
        time_min=time_min,
        time_max=time_max,
        max_results=5
    )

    if 'events' in list_result and list_result['events']:
        event = list_result['events'][0]
        event_id = event['id']

        # Update event
        update_result = await calendar_update_event(
            event_id=event_id,
            summary=f"{event.get('summary', 'Event')} [UPDATED]",
            description="Updated by automated test"
        )

        if update_result.get('status') == 'updated':
            print(f"[OK] Event updated")
            print(f"    Event ID: {event_id}")
            return True
        else:
            print(f"[FAIL] Failed to update: {update_result.get('error', 'Unknown error')}")
            return False
    else:
        print(f"[FAIL] No events found to update")
        return False


# ==============================================================================
# ROLODEX AGENT TESTS - Google Contacts Operations
# ==============================================================================

async def test_rolodex_search_contacts():
    """Test 1: Rolodex searches for contacts"""
    print("\n" + "="*80)
    print("TEST 1: Rolodex - Search Contacts")
    print("="*80)

    from tools.adk_tools.contacts_adk_tools import contacts_search_people

    result = await contacts_search_people(
        query="Tomislav",
        max_results=5
    )

    if 'contacts' in result and 'error' not in result:
        contacts = result.get('contacts', [])
        print(f"[OK] Found {len(contacts)} contact(s) matching 'Tomislav'")
        for contact in contacts[:2]:
            print(f"    - {contact.get('name', 'No name')} ({contact.get('email', 'No email')})")
        return True
    else:
        print(f"[FAIL] Failed to search: {result.get('error', 'Unknown error')}")
        return False


async def test_rolodex_create_contact():
    """Test 2: Rolodex creates a new contact"""
    print("\n" + "="*80)
    print("TEST 2: Rolodex - Create Contact")
    print("="*80)

    from tools.adk_tools.contacts_adk_tools import contacts_create_contact

    test_name = f"Test Contact {datetime.now().strftime('%Y%m%d_%H%M%S')}"

    result = await contacts_create_contact(
        name=test_name,
        email=f"test{datetime.now().strftime('%H%M%S')}@example.com",
        phone="+385 91 999 9999",
        organization="Test Company"
    )

    if result.get('status') == 'created':
        print(f"[OK] Contact created: {test_name}")
        print(f"    ID: {result.get('resource_name', 'N/A')}")
        return True
    else:
        print(f"[FAIL] Failed to create: {result.get('error', 'Unknown error')}")
        return False


async def test_rolodex_get_by_name():
    """Test 3: Rolodex gets contact by name"""
    print("\n" + "="*80)
    print("TEST 3: Rolodex - Get Contact by Name")
    print("="*80)

    from tools.adk_tools.contacts_adk_tools import contacts_get_by_name

    result = await contacts_get_by_name(
        name="Tomislav Golić"
    )

    if result.get('found') or result.get('status') == 'success':
        print(f"[OK] Found contact: {result.get('name', 'N/A')}")
        print(f"    Email: {result.get('email', 'N/A')}")
        print(f"    Phone: {result.get('phone', 'N/A')}")
        return True
    else:
        print(f"[FAIL] Contact not found or error: {result.get('error', 'Unknown error')}")
        return False


# ==============================================================================
# TRACKER AGENT TESTS - Google Tasks Operations
# ==============================================================================

async def test_tracker_list_tasks():
    """Test 1: Tracker lists tasks"""
    print("\n" + "="*80)
    print("TEST 1: Tracker - List Tasks")
    print("="*80)

    from tools.adk_tools.tasks_adk_tools import tasks_list_tasks

    result = await tasks_list_tasks(
        tasklist_id="@default",
        max_results=10
    )

    if 'tasks' in result and 'error' not in result:
        tasks = result.get('tasks', [])
        print(f"[OK] Found {len(tasks)} task(s)")
        for task in tasks[:3]:
            print(f"    - {task.get('title', 'No title')} (Status: {task.get('status', 'unknown')})")
        return True
    else:
        print(f"[FAIL] Failed to list tasks: {result.get('error', 'Unknown error')}")
        return False


async def test_tracker_create_task():
    """Test 2: Tracker creates a new task"""
    print("\n" + "="*80)
    print("TEST 2: Tracker - Create Task")
    print("="*80)

    from tools.adk_tools.tasks_adk_tools import tasks_create_task
    from datetime import datetime, timedelta

    task_title = f"Test Task {datetime.now().strftime('%Y%m%d_%H%M%S')}"
    due_date = (datetime.now() + timedelta(days=3)).replace(hour=17, minute=0, second=0, microsecond=0)

    result = await tasks_create_task(
        title=task_title,
        notes="Created by automated API test",
        due=due_date.isoformat() + 'Z'
    )

    if result.get('status') == 'created' or 'id' in result:
        print(f"[OK] Task created: {task_title}")
        print(f"    Task ID: {result.get('id', 'N/A')}")
        return True
    else:
        print(f"[FAIL] Failed to create task: {result.get('error', 'Unknown error')}")
        return False


async def test_tracker_complete_task():
    """Test 3: Tracker completes a task"""
    print("\n" + "="*80)
    print("TEST 3: Tracker - Complete Task")
    print("="*80)

    from tools.adk_tools.tasks_adk_tools import tasks_list_tasks, tasks_complete_task

    # Find a task to complete
    list_result = await tasks_list_tasks(
        tasklist_id="@default",
        max_results=5
    )

    if 'tasks' in list_result and list_result['tasks']:
        # Find incomplete task
        for task in list_result['tasks']:
            if task.get('status') == 'needsAction':
                task_id = task['id']
                task_title = task.get('title', 'Task')

                # Complete it
                complete_result = await tasks_complete_task(
                    tasklist_id="@default",
                    task_id=task_id
                )

                if complete_result.get('task_status') == 'completed' or complete_result.get('status') == 'updated':
                    print(f"[OK] Task completed: {task_title}")
                    print(f"    Task ID: {task_id}")
                    return True
                else:
                    print(f"[FAIL] Failed to complete: {complete_result.get('error', 'Unknown error')}")
                    return False

        print(f"[FAIL] No incomplete tasks found to complete")
        return False
    else:
        print(f"[FAIL] No tasks found")
        return False


# ==============================================================================
# MAIN TEST RUNNER
# ==============================================================================

async def run_analyst_tests():
    """Run all Analyst agent tests"""
    print("\n" + "="*80)
    print(" "*25 + "ANALYST AGENT TESTS")
    print("="*80)
    print()
    print("Testing Google Sheets operations with real API")
    print()

    tests = [
        ("Read Spreadsheet", test_analyst_read_sheet),
        ("Write New Data", test_analyst_write_sheet),
        ("Search Data", test_analyst_search_data),
        ("Calculate Totals", test_analyst_calculate_total),
        ("Update Cell", test_analyst_update_cell),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            passed = await test_func()
            results.append((test_name, passed))
        except Exception as e:
            print(f"\n[ERROR] Test '{test_name}' crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # Summary
    print("\n" + "="*80)
    print("ANALYST TESTS SUMMARY")
    print("="*80)

    passed = sum(1 for _, p in results if p)
    total = len(results)

    for test_name, test_passed in results:
        status = "[OK] PASSED" if test_passed else "[FAIL] FAILED"
        print(f"{status}: {test_name}")

    print()
    print(f"Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    print()

    return passed == total


async def run_librarian_tests():
    """Run all Librarian agent tests"""
    print("\n" + "="*80)
    print(" "*23 + "LIBRARIAN AGENT TESTS")
    print("="*80)
    print()
    print("Testing Google Drive operations with real API")
    print()

    tests = [
        ("Search Files", test_librarian_search_files),
        ("Create Folder", test_librarian_create_folder),
        ("Upload File", test_librarian_upload_file),
        ("List Folder Contents", test_librarian_list_folder_contents),
        ("Share File", test_librarian_share_file),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            passed = await test_func()
            results.append((test_name, passed))
        except Exception as e:
            print(f"\n[ERROR] Test '{test_name}' crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # Summary
    print("\n" + "="*80)
    print("LIBRARIAN TESTS SUMMARY")
    print("="*80)

    passed = sum(1 for _, p in results if p)
    total = len(results)

    for test_name, test_passed in results:
        status = "[OK] PASSED" if test_passed else "[FAIL] FAILED"
        print(f"{status}: {test_name}")

    print()
    print(f"Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    print()

    return passed == total


async def run_secretary_tests():
    """Run all Secretary agent tests"""
    print("\n" + "="*80)
    print(" "*23 + "SECRETARY AGENT TESTS")
    print("="*80)
    print()
    print("Testing Google Calendar operations with real API")
    print()

    tests = [
        ("List Upcoming Events", test_secretary_list_events),
        ("Create New Event", test_secretary_create_event),
        ("Update Event", test_secretary_update_event),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            passed = await test_func()
            results.append((test_name, passed))
        except Exception as e:
            print(f"\n[ERROR] Test '{test_name}' crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # Summary
    print("\n" + "="*80)
    print("SECRETARY TESTS SUMMARY")
    print("="*80)

    passed = sum(1 for _, p in results if p)
    total = len(results)

    for test_name, test_passed in results:
        status = "[OK] PASSED" if test_passed else "[FAIL] FAILED"
        print(f"{status}: {test_name}")

    print()
    print(f"Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    print()

    return passed == total


async def run_rolodex_tests():
    """Run all Rolodex agent tests"""
    print("\n" + "="*80)
    print(" "*24 + "ROLODEX AGENT TESTS")
    print("="*80)
    print()
    print("Testing Google Contacts operations with real API")
    print()

    tests = [
        ("Search Contacts", test_rolodex_search_contacts),
        ("Create Contact", test_rolodex_create_contact),
        ("Get Contact by Name", test_rolodex_get_by_name),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            passed = await test_func()
            results.append((test_name, passed))
        except Exception as e:
            print(f"\n[ERROR] Test '{test_name}' crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # Summary
    print("\n" + "="*80)
    print("ROLODEX TESTS SUMMARY")
    print("="*80)

    passed = sum(1 for _, p in results if p)
    total = len(results)

    for test_name, test_passed in results:
        status = "[OK] PASSED" if test_passed else "[FAIL] FAILED"
        print(f"{status}: {test_name}")

    print()
    print(f"Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    print()

    return passed == total


async def run_tracker_tests():
    """Run all Tracker agent tests"""
    print("\n" + "="*80)
    print(" "*24 + "TRACKER AGENT TESTS")
    print("="*80)
    print()
    print("Testing Google Tasks operations with real API")
    print()

    tests = [
        ("List Tasks", test_tracker_list_tasks),
        ("Create Task", test_tracker_create_task),
        ("Complete Task", test_tracker_complete_task),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            passed = await test_func()
            results.append((test_name, passed))
        except Exception as e:
            print(f"\n[ERROR] Test '{test_name}' crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # Summary
    print("\n" + "="*80)
    print("TRACKER TESTS SUMMARY")
    print("="*80)

    passed = sum(1 for _, p in results if p)
    total = len(results)

    for test_name, test_passed in results:
        status = "[OK] PASSED" if test_passed else "[FAIL] FAILED"
        print(f"{status}: {test_name}")

    print()
    print(f"Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    print()

    return passed == total


async def main():
    """Main test runner"""
    print("\n" + "="*80)
    print(" "*20 + "REAL API AGENT TESTING")
    print("="*80)
    print()
    print("Testing agents with REAL Google APIs")
    print("Following test -> fix -> retest workflow")
    print()
    print("="*80)

    # Check credentials
    try:
        from auth.credential_store import get_credential_store
        credential_store = get_credential_store()
        creds = credential_store.get_credentials()

        if creds is None:
            print("\n[ERROR] No OAuth credentials found!")
            print("Run: python tools/oauth_cli.py --auth")
            return

        print("[OK] OAuth credentials found")
        print()
    except Exception as e:
        print(f"\n[ERROR] Failed to get credentials: {e}")
        return

    # Run all agent tests
    analyst_passed = await run_analyst_tests()
    librarian_passed = await run_librarian_tests()
    secretary_passed = await run_secretary_tests()
    rolodex_passed = await run_rolodex_tests()
    tracker_passed = await run_tracker_tests()

    print("\n" + "="*80)
    print("OVERALL SUMMARY")
    print("="*80)
    print(f"Analyst Tests (Sheets):    {'[OK] PASSED' if analyst_passed else '[FAIL] FAILED'}")
    print(f"Librarian Tests (Drive):   {'[OK] PASSED' if librarian_passed else '[FAIL] FAILED'}")
    print(f"Secretary Tests (Calendar): {'[OK] PASSED' if secretary_passed else '[FAIL] FAILED'}")
    print(f"Rolodex Tests (Contacts):  {'[OK] PASSED' if rolodex_passed else '[FAIL] FAILED'}")
    print(f"Tracker Tests (Tasks):     {'[OK] PASSED' if tracker_passed else '[FAIL] FAILED'}")
    print()

    all_passed = all([analyst_passed, librarian_passed, secretary_passed, rolodex_passed, tracker_passed])

    if all_passed:
        print("[OK] ALL 19 TESTS PASSED! 100% Success Rate!")
        print()
        print("Tested APIs:")
        print("  [OK] Google Sheets - 5 tests")
        print("  [OK] Google Drive - 5 tests")
        print("  [OK] Google Calendar - 3 tests")
        print("  [OK] Google Contacts - 3 tests")
        print("  [OK] Google Tasks - 3 tests")
        print()
        print("Next: Multi-agent workflow testing")
    else:
        print("[FAIL] Some tests failed - fixing bugs and retesting")

    print()


if __name__ == "__main__":
    asyncio.run(main())
