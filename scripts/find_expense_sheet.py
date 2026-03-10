"""Find and verify Ulazni računi 2025 sheet"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools.drive_navigator import get_drive_navigator
from tools.api_implementations.drive_api import drive_search_files
from tools.api_implementations.sheets_api import sheets_get_values
from tools.google_api_client import create_api_client_auto

async def main():
    nav = await get_drive_navigator()
    folder_id = nav.get_folder_id('expense_receipts')
    print(f'Expense_Receipts Folder ID: {folder_id}')

    creds = create_api_client_auto().credentials

    # Find spreadsheets
    result = await drive_search_files(
        creds,
        f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
    )

    files = result.get('files', [])
    print(f'\nFound {len(files)} spreadsheet(s):')
    for f in files:
        print(f"  - {f['name']} (ID: {f['id']})")

        # Read header row
        try:
            sheet_result = await sheets_get_values(creds, f['id'], 'A1:H1')
            headers = sheet_result.get('values', [[]])[0]
            print(f"    Headers: {headers}")
        except Exception as e:
            print(f"    Error reading: {e}")

asyncio.run(main())
