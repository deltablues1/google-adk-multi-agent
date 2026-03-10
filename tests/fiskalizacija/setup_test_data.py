"""
Setup Test Data for Real API Testing

This script creates test data in Google services for testing all agents:
1. Google Sheets - Test spreadsheet with sample data (Analyst)
2. Google Drive - Test folder structure (Librarian)
3. Google Contacts - Test contact entry (Rolodex)
4. Google Calendar - Test events (Secretary)
5. Google Tasks - Test tasks (Tracker)

Run this ONCE before running agent tests.
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from tools.adk_tools.sheets_adk_tools import (
    sheets_create_spreadsheet,
    sheets_update_values
)
from tools.adk_tools.drive_adk_tools import (
    drive_create_folder,
    drive_upload_file
)
from tools.adk_tools.contacts_adk_tools import (
    contacts_create_contact
)
from tools.adk_tools.calendar_adk_tools import (
    calendar_create_event
)
from tools.adk_tools.tasks_adk_tools import (
    tasks_create_task
)


async def setup_sheets_test_data():
    """Create test Google Sheet with sample data."""
    print("\n" + "="*80)
    print("STEP 1: Creating Test Google Sheet")
    print("="*80)

    # Create spreadsheet
    sheet_name = f"Test Data 2026 - {datetime.now().strftime('%Y%m%d_%H%M%S')}"

    create_result = await sheets_create_spreadsheet(
        title=sheet_name,
        sheet_titles=["Sales Data", "Expenses", "Contacts"]
    )

    if create_result.get('status') == 'created':
        spreadsheet_id = create_result['spreadsheet_id']
        sheet_url = create_result['spreadsheet_url']
        print(f"[OK] Spreadsheet created: {sheet_name}")
        print(f"    ID: {spreadsheet_id}")
        print(f"    URL: {sheet_url}")

        # Add sample data to Sales Data sheet
        sales_data = [
            ["Date", "Product", "Quantity", "Price", "Total"],
            ["2026-01-15", "IT Consulting", "10", "150.00", "1500.00"],
            ["2026-01-20", "Software License", "5", "300.00", "1500.00"],
            ["2026-01-25", "Training Services", "8", "200.00", "1600.00"],
            ["2026-01-28", "Support Package", "3", "500.00", "1500.00"],
        ]

        write_result = await sheets_update_values(
            spreadsheet_id=spreadsheet_id,
            range="Sales Data!A1:E5",
            values=sales_data
        )

        if write_result.get('status') == 'updated':
            print(f"[OK] Sample sales data added")

        # Add sample data to Expenses sheet
        expenses_data = [
            ["Date", "Category", "Description", "Amount"],
            ["2026-01-10", "Office", "Rent January", "2000.00"],
            ["2026-01-15", "Software", "Azure subscription", "500.00"],
            ["2026-01-18", "Marketing", "Google Ads", "300.00"],
            ["2026-01-22", "Utilities", "Electricity", "150.00"],
        ]

        write_result = await sheets_update_values(
            spreadsheet_id=spreadsheet_id,
            range="Expenses!A1:D5",
            values=expenses_data
        )

        if write_result.get('status') == 'updated':
            print(f"[OK] Sample expenses data added")

        # Add sample contacts
        contacts_data = [
            ["Name", "Email", "Phone", "Company"],
            ["Tomislav Golić", "tgolic555@gmail.com", "+385 91 234 5678", "LUX TECH"],
            ["Ivan Horvat", "ivan@example.com", "+385 91 111 2222", "Test Corp"],
            ["Ana Marić", "ana@example.com", "+385 91 333 4444", "Demo Ltd"],
        ]

        write_result = await sheets_update_values(
            spreadsheet_id=spreadsheet_id,
            range="Contacts!A1:D4",
            values=contacts_data
        )

        if write_result.get('status') == 'updated':
            print(f"[OK] Sample contacts data added")

        print()
        return {
            "success": True,
            "spreadsheet_id": spreadsheet_id,
            "spreadsheet_url": sheet_url,
            "sheet_name": sheet_name
        }
    else:
        print(f"[FAIL] Failed to create spreadsheet: {create_result.get('error')}")
        return {"success": False, "error": create_result.get('error')}


async def setup_drive_test_data():
    """Create test Drive folder structure."""
    print("\n" + "="*80)
    print("STEP 2: Creating Test Drive Folders")
    print("="*80)

    # Create main test folder
    folder_result = await drive_create_folder(
        folder_name="Test Documents 2026",
        parent_folder_id=None
    )

    if folder_result.get('status') == 'created':
        main_folder_id = folder_result['id']
        folder_url = folder_result.get('web_view_link', '')
        print(f"[OK] Main folder created: Test Documents 2026")
        print(f"    ID: {main_folder_id}")
        print(f"    URL: {folder_url}")

        # Create subfolder for invoices
        subfolder_result = await drive_create_folder(
            folder_name="Invoices",
            parent_folder_id=main_folder_id
        )

        invoices_folder_id = None
        if subfolder_result.get('status') == 'created':
            invoices_folder_id = subfolder_result['id']
            print(f"[OK] Subfolder created: Invoices")

        # Create subfolder for reports
        reports_result = await drive_create_folder(
            folder_name="Reports",
            parent_folder_id=main_folder_id
        )

        reports_folder_id = None
        if reports_result.get('status') == 'created':
            reports_folder_id = reports_result['id']
            print(f"[OK] Subfolder created: Reports")

        print()
        return {
            "success": True,
            "main_folder_id": main_folder_id,
            "main_folder_url": folder_url,
            "invoices_folder_id": invoices_folder_id,
            "reports_folder_id": reports_folder_id
        }
    else:
        print(f"[FAIL] Failed to create folder: {folder_result.get('error')}")
        return {"success": False, "error": folder_result.get('error')}


async def setup_contacts_test_data():
    """Create test contact entry."""
    print("\n" + "="*80)
    print("STEP 3: Creating Test Contact")
    print("="*80)

    # Create Tomislav Golić contact
    contact_result = await contacts_create_contact(
        name="Tomislav Golić",
        email="tgolic555@gmail.com",
        phone="+385 91 234 5678",
        organization="LUX TECH"
    )

    if contact_result.get('status') == 'created':
        contact_id = contact_result.get('resource_name', '')
        print(f"[OK] Contact created: Tomislav Golić")
        print(f"    ID: {contact_id}")
        print(f"    Email: tgolic555@gmail.com")
        print(f"    Phone: +385 91 234 5678")
        print()
        return {
            "success": True,
            "contact_id": contact_id
        }
    else:
        print(f"[FAIL] Failed to create contact: {contact_result.get('error')}")
        print()
        return {"success": False, "error": contact_result.get('error')}


async def setup_calendar_test_data():
    """Create test calendar events."""
    print("\n" + "="*80)
    print("STEP 4: Creating Test Calendar Events")
    print("="*80)

    # Event 1: Tomorrow at 10:00
    tomorrow = datetime.now() + timedelta(days=1)
    event1_start = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
    event1_end = event1_start + timedelta(hours=1)

    event1_result = await calendar_create_event(
        summary="Team Meeting - Q1 Planning",
        start_time=event1_start.isoformat(),
        end_time=event1_end.isoformat(),
        description="Quarterly planning meeting for Q1 2026",
        attendees=["tgolic555@gmail.com"]
    )

    event1_id = None
    if event1_result.get('status') == 'created':
        event1_id = event1_result.get('event_id')
        print(f"[OK] Event 1 created: Team Meeting - Q1 Planning")
        print(f"    Time: {event1_start.strftime('%Y-%m-%d %H:%M')}")
        print(f"    ID: {event1_id}")

    # Event 2: Next week at 14:00
    next_week = datetime.now() + timedelta(days=7)
    event2_start = next_week.replace(hour=14, minute=0, second=0, microsecond=0)
    event2_end = event2_start + timedelta(hours=2)

    event2_result = await calendar_create_event(
        summary="Client Presentation - New Project",
        start_time=event2_start.isoformat(),
        end_time=event2_end.isoformat(),
        description="Present new project proposal to client",
        attendees=["tgolic555@gmail.com"]
    )

    event2_id = None
    if event2_result.get('status') == 'created':
        event2_id = event2_result.get('event_id')
        print(f"[OK] Event 2 created: Client Presentation")
        print(f"    Time: {event2_start.strftime('%Y-%m-%d %H:%M')}")
        print(f"    ID: {event2_id}")

    print()
    return {
        "success": True,
        "event1_id": event1_id,
        "event2_id": event2_id
    }


async def setup_tasks_test_data():
    """Create test tasks."""
    print("\n" + "="*80)
    print("STEP 5: Creating Test Tasks")
    print("="*80)

    # Task 1: High priority
    tomorrow = datetime.now() + timedelta(days=1)
    tomorrow_due = tomorrow.replace(hour=17, minute=0, second=0, microsecond=0)

    task1_result = await tasks_create_task(
        title="Complete Q1 financial report",
        notes="Gather all Q1 data and prepare comprehensive report",
        due=tomorrow_due.isoformat() + 'Z'
    )

    task1_id = None
    if task1_result.get('status') == 'created':
        task1_id = task1_result.get('task_id')
        print(f"[OK] Task 1 created: Complete Q1 financial report")
        print(f"    Due: {tomorrow.strftime('%Y-%m-%d')}")
        print(f"    ID: {task1_id}")

    # Task 2: Medium priority
    next_week = datetime.now() + timedelta(days=7)
    next_week_due = next_week.replace(hour=17, minute=0, second=0, microsecond=0)

    task2_result = await tasks_create_task(
        title="Review and update client contracts",
        notes="Review all active client contracts and update terms if needed",
        due=next_week_due.isoformat() + 'Z'
    )

    task2_id = None
    if task2_result.get('status') == 'created':
        task2_id = task2_result.get('task_id')
        print(f"[OK] Task 2 created: Review client contracts")
        print(f"    Due: {next_week.strftime('%Y-%m-%d')}")
        print(f"    ID: {task2_id}")

    # Task 3: Low priority
    next_month = datetime.now() + timedelta(days=30)
    next_month_due = next_month.replace(hour=17, minute=0, second=0, microsecond=0)

    task3_result = await tasks_create_task(
        title="Plan team building event",
        notes="Organize team building activity for March",
        due=next_month_due.isoformat() + 'Z'
    )

    task3_id = None
    if task3_result.get('status') == 'created':
        task3_id = task3_result.get('task_id')
        print(f"[OK] Task 3 created: Plan team building event")
        print(f"    Due: {next_month.strftime('%Y-%m-%d')}")
        print(f"    ID: {task3_id}")

    print()
    return {
        "success": True,
        "task1_id": task1_id,
        "task2_id": task2_id,
        "task3_id": task3_id
    }


async def main():
    """Run all test data setup."""
    print("\n" + "="*80)
    print(" "*20 + "TEST DATA SETUP")
    print("="*80)
    print()
    print("This will create test data in your Google account:")
    print("  - 1 Google Sheet with sample data")
    print("  - Test folder structure in Drive")
    print("  - 1 contact (Tomislav Golić)")
    print("  - 2 calendar events")
    print("  - 3 tasks")
    print()
    print("="*80)

    results = {}

    # Check credentials first
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

    # Setup all test data
    try:
        # Sheets
        sheets_result = await setup_sheets_test_data()
        results['sheets'] = sheets_result

        # Drive
        drive_result = await setup_drive_test_data()
        results['drive'] = drive_result

        # Contacts
        contacts_result = await setup_contacts_test_data()
        results['contacts'] = contacts_result

        # Calendar
        calendar_result = await setup_calendar_test_data()
        results['calendar'] = calendar_result

        # Tasks
        tasks_result = await setup_tasks_test_data()
        results['tasks'] = tasks_result

    except Exception as e:
        print(f"\n[ERROR] Setup failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Summary
    print("\n" + "="*80)
    print("SETUP COMPLETE - SUMMARY")
    print("="*80)
    print()

    if results.get('sheets', {}).get('success'):
        print(f"[OK] Google Sheet: {results['sheets']['sheet_name']}")
        print(f"    URL: {results['sheets']['spreadsheet_url']}")
    else:
        print(f"[FAIL] Google Sheet: {results.get('sheets', {}).get('error', 'Unknown error')}")

    if results.get('drive', {}).get('success'):
        print(f"[OK] Drive Folder: Test Documents 2026")
        print(f"    URL: {results['drive']['main_folder_url']}")
    else:
        print(f"[FAIL] Drive Folder: {results.get('drive', {}).get('error', 'Unknown error')}")

    if results.get('contacts', {}).get('success'):
        print(f"[OK] Contact: Tomislav Golić (tgolic555@gmail.com)")
    else:
        print(f"[FAIL] Contact: {results.get('contacts', {}).get('error', 'Unknown error')}")

    if results.get('calendar', {}).get('success'):
        print(f"[OK] Calendar Events: 2 events created")
    else:
        print(f"[FAIL] Calendar Events: {results.get('calendar', {}).get('error', 'Unknown error')}")

    if results.get('tasks', {}).get('success'):
        print(f"[OK] Tasks: 3 tasks created")
    else:
        print(f"[FAIL] Tasks: {results.get('tasks', {}).get('error', 'Unknown error')}")

    print()
    print("="*80)
    print("[OK] Test data setup complete!")
    print()
    print("Next: Run agent tests with real APIs")
    print("  python test_real_api_agents.py")
    print()


if __name__ == "__main__":
    asyncio.run(main())
