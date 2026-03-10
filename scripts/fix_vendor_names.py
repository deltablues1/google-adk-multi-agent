"""
Fix Vendor Names in Firestore and Google Sheets

Updates vendor names for existing expense records using OIB-based mapping.
This script fixes OCR errors where vendor names were extracted incorrectly.

Usage:
    py scripts/fix_vendor_names.py
"""

import asyncio
import sys
import os
from dotenv import load_dotenv

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Fix encoding on Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Load environment
load_dotenv()

# Known vendor mapping (same as in batch_process_invoices.py)
KNOWN_VENDORS = {
    'HR95243482140': 'SMIT-COMMERCE d.o.o.',
    'HR46108893754': 'SPAR HRVATSKA d.o.o.',
    'HR29524210204': 'A1 Hrvatska d.o.o.',
    'HR36365310424': 'SCHRACK TECHNIK d.o.o.',
    'HR16372522596': 'TEVETRON d.o.o.',
    'HR52101284898': 'ZELENI ELEMENTI d.o.o.',
    'HR20246776105': 'Arrslog d.o.o.',
    'HR43227166836': 'MIKROTRON d.o.o.',
    'HR71814187727': 'FDS TRGOVINA d.o.o.',
    'HR18290972213': 'ELMATIS d.o.o.',
}


async def fix_firestore_vendors():
    """Fix vendor names in Firestore expense-records collection"""
    from tools.database.database_handler import get_database_handler

    db = get_database_handler()

    print("\n🔍 Scanning Firestore expense-records...")

    # Get all expense records
    records = await db.query_documents("expense-records", filters=[], limit=1000)

    print(f"   Found {len(records)} records")

    updated_count = 0
    errors = []

    for record in records:
        doc_id = record.get('_id')
        vendor = record.get('vendor', '')
        tax_id = record.get('tax_id', '')

        if not doc_id:
            continue

        # Skip records without tax_id (like Erste Bank)
        if not tax_id:
            continue

        # Check if this OIB has a known canonical name
        if tax_id in KNOWN_VENDORS:
            canonical_name = KNOWN_VENDORS[tax_id]

            # Compare exactly (not case-insensitive) to catch differences like "D.0.0." vs "d.o.o."
            if canonical_name != vendor:
                print(f"\n   📝 Fixing: '{vendor}' → '{canonical_name}'")
                print(f"      Doc ID: {doc_id}")
                print(f"      Invoice: {record.get('invoice_number')}")
                print(f"      OIB: {tax_id}")

                try:
                    # Update Firestore document using direct client access
                    doc_ref = db.client.collection("expense-records").document(doc_id)
                    doc_ref.update({"vendor": canonical_name})

                    updated_count += 1
                    print(f"      ✅ Updated in Firestore")

                except Exception as e:
                    error_msg = f"Failed to update {doc_id}: {e}"
                    errors.append(error_msg)
                    print(f"      ❌ Error: {e}")

    print(f"\n✅ Firestore: Updated {updated_count} vendor names")

    if errors:
        print(f"\n⚠️  Errors encountered: {len(errors)}")
        for error in errors:
            print(f"   - {error}")

    return updated_count


async def fix_sheets_vendors():
    """Fix vendor names in Google Sheets"""
    from tools.api_implementations.sheets_api import sheets_get_values, sheets_update_values
    from tools.google_api_client import create_api_client_auto
    from tools.drive_navigator import get_drive_navigator

    print("\n🔍 Scanning Google Sheets...")

    # Get sheet ID
    navigator = await get_drive_navigator()
    folder_id = navigator.get_folder_id('expense_receipts')

    if not folder_id:
        print("   ❌ Error: expense_receipts folder not found")
        return 0

    # Find the sheet
    from tools.api_implementations.drive_api import drive_search_files
    credentials = create_api_client_auto().credentials

    result = await drive_search_files(
        credentials,
        f"'{folder_id}' in parents and name='Ulazni računi 2025' and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
    )

    files = result.get('files', [])
    if not files:
        print("   ❌ Error: 'Ulazni računi 2025' sheet not found")
        return 0

    sheet_id = files[0]['id']
    print(f"   Found sheet: {files[0]['name']}")

    # Read all data
    sheet_data = await sheets_get_values(credentials, sheet_id, "A:H")
    rows = sheet_data.get('values', [])

    if not rows:
        print("   ⚠️  Sheet is empty")
        return 0

    # Header: RedBr, BrojRacuna, Datum, Dobavljac, OIB, Osnovica, PDV, Ukupno
    # Columns: A(0)=RedBr, B(1)=BrojRacuna, C(2)=Datum, D(3)=Dobavljac, E(4)=OIB, F(5)=Osnovica, G(6)=PDV, H(7)=Ukupno

    updated_count = 0
    updates = []

    for i, row in enumerate(rows[1:], start=2):  # Skip header, start at row 2
        if len(row) < 5:
            continue

        vendor = row[3] if len(row) > 3 else ''
        oib = row[4] if len(row) > 4 else ''

        if not oib:
            continue

        # Check if this OIB has a known canonical name
        if oib in KNOWN_VENDORS:
            canonical_name = KNOWN_VENDORS[oib]

            # If names differ, prepare update
            if canonical_name.lower() != vendor.lower():
                invoice_num = row[1] if len(row) > 1 else ''
                print(f"\n   📝 Fixing row {i}: '{vendor}' → '{canonical_name}'")
                print(f"      Invoice: {invoice_num}")
                print(f"      OIB: {oib}")

                # Prepare update (update only column D - Dobavljac)
                updates.append({
                    'row': i,
                    'range': f"D{i}",
                    'value': canonical_name
                })

    # Apply updates
    if updates:
        print(f"\n   Applying {len(updates)} updates to Google Sheets...")

        for update in updates:
            try:
                await sheets_update_values(
                    credentials,
                    sheet_id,
                    update['range'],
                    [[update['value']]],
                    value_input_option="RAW"
                )
                updated_count += 1
                print(f"      ✅ Updated row {update['row']}")

            except Exception as e:
                print(f"      ❌ Error updating row {update['row']}: {e}")

    print(f"\n✅ Google Sheets: Updated {updated_count} vendor names")

    return updated_count


async def main():
    import sys

    print("=" * 70)
    print("Fix Vendor Names - Firestore & Google Sheets")
    print("=" * 70)

    print("\nThis script will update vendor names using OIB-based mapping.")
    print("\nKnown vendors:")
    for oib, name in KNOWN_VENDORS.items():
        print(f"   {oib} → {name}")

    # Check for --yes flag
    auto_yes = '--yes' in sys.argv or '-y' in sys.argv

    if not auto_yes:
        # Confirm
        response = input("\n❓ Proceed with updates? (yes/no): ")

        if response.lower() != 'yes':
            print("\n❌ Cancelled.")
            return

    print("\n🚀 Starting updates...\n")

    # Fix Firestore
    firestore_count = await fix_firestore_vendors()

    # Fix Google Sheets
    sheets_count = await fix_sheets_vendors()

    # Summary
    print("\n" + "=" * 70)
    print("UPDATE SUMMARY")
    print("=" * 70)
    print(f"\n✅ Firestore records updated: {firestore_count}")
    print(f"✅ Google Sheets rows updated: {sheets_count}")
    print(f"\n💡 Total vendor names fixed: {firestore_count + sheets_count}")
    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
