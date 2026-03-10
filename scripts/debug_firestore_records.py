"""
Debug Firestore Records

Displays the contents of expense-records to see what fields are actually stored.

Usage:
    py scripts/debug_firestore_records.py
"""

import asyncio
import sys
import os
import json
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


async def main():
    from tools.database.database_handler import get_database_handler

    db = get_database_handler()

    print("\n" + "=" * 70)
    print("Firestore Expense Records - Debug View")
    print("=" * 70)

    # Get all expense records
    records = await db.query_documents("expense-records", filters=[], limit=50)

    print(f"\n📊 Found {len(records)} records\n")

    if not records:
        print("⚠️  No records found!")
        return

    # Show first 5 records in detail
    print("=" * 70)
    print("SAMPLE RECORDS (first 5)")
    print("=" * 70)

    for i, record in enumerate(records[:5], 1):
        doc_id = record.get('_id', 'NO_ID')
        vendor = record.get('vendor', 'NO_VENDOR')
        invoice = record.get('invoice_number', 'NO_INVOICE')
        tax_id = record.get('tax_id', 'NO_TAX_ID')
        amount = record.get('amount', 0)

        print(f"\n[{i}] Document ID: {doc_id}")
        print(f"    Vendor: {vendor}")
        print(f"    Invoice: {invoice}")
        print(f"    Tax ID: {tax_id}")
        print(f"    Amount: {amount}")
        print(f"    All fields: {list(record.keys())}")

    # Check which records have tax_id
    print("\n" + "=" * 70)
    print("TAX_ID FIELD ANALYSIS")
    print("=" * 70)

    has_tax_id = [r for r in records if 'tax_id' in r and r.get('tax_id')]
    missing_tax_id = [r for r in records if 'tax_id' not in r or not r.get('tax_id')]

    print(f"\n✅ Records WITH tax_id field: {len(has_tax_id)}/{len(records)}")
    print(f"❌ Records WITHOUT tax_id field: {len(missing_tax_id)}/{len(records)}")

    if missing_tax_id:
        print(f"\n⚠️  Records missing tax_id:")
        for record in missing_tax_id[:10]:  # Show first 10
            print(f"   - {record.get('vendor', 'Unknown')} | Invoice: {record.get('invoice_number', 'N/A')}")

    # Show all unique field names across all records
    all_fields = set()
    for record in records:
        all_fields.update(record.keys())

    print("\n" + "=" * 70)
    print("ALL FIELDS FOUND IN COLLECTION")
    print("=" * 70)
    print(f"\n{sorted(all_fields)}")

    # Show a complete record dump for debugging
    if records:
        print("\n" + "=" * 70)
        print("COMPLETE RECORD DUMP (first record)")
        print("=" * 70)
        print(json.dumps(records[0], indent=2, default=str))

    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
