"""
List Vendors by OIB

Shows which vendor names are used for each OIB in Firestore.
Helps identify OCR inconsistencies.

Usage:
    py scripts/list_vendors_by_oib.py
"""

import asyncio
import sys
import os
from collections import defaultdict
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

# Known canonical names
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


async def main():
    from tools.database.database_handler import get_database_handler

    db = get_database_handler()

    print("\n" + "=" * 70)
    print("Vendors by OIB - Firestore Analysis")
    print("=" * 70)

    # Get all expense records
    records = await db.query_documents("expense-records", filters=[], limit=1000)

    print(f"\n📊 Total records: {len(records)}\n")

    # Group by OIB
    by_oib = defaultdict(list)

    for record in records:
        oib = record.get('tax_id', 'NO_OIB')
        vendor = record.get('vendor', 'Unknown')
        invoice = record.get('invoice_number', 'N/A')
        doc_id = record.get('_id', 'N/A')

        by_oib[oib].append({
            'vendor': vendor,
            'invoice': invoice,
            'doc_id': doc_id
        })

    # Display analysis
    print("=" * 70)
    print("VENDOR NAMES BY OIB")
    print("=" * 70)

    needs_fixing = []

    # Sort OIBs, handling None values
    sorted_oibs = sorted([k for k in by_oib.keys() if k is not None and k != 'NO_OIB'])

    # Add None/NO_OIB at the end
    if None in by_oib or 'NO_OIB' in by_oib:
        sorted_oibs.extend([k for k in by_oib.keys() if k is None or k == 'NO_OIB'])

    for oib in sorted_oibs:
        entries = by_oib[oib]
        unique_names = set(e['vendor'] for e in entries)

        print(f"\n🔑 OIB: {oib}")
        print(f"   📝 {len(entries)} invoice(s), {len(unique_names)} unique name(s)")

        # Check if canonical name exists for this OIB
        canonical = KNOWN_VENDORS.get(oib)

        if canonical:
            print(f"   ✅ Canonical name: {canonical}")

            # Show all variants
            for name in sorted(unique_names):
                count = sum(1 for e in entries if e['vendor'] == name)

                # Check if name matches canonical (case-insensitive)
                if name.lower() == canonical.lower():
                    print(f"      ✓ '{name}' ({count}x) - CORRECT")
                else:
                    print(f"      ✗ '{name}' ({count}x) - NEEDS FIX")

                    # Add to fix list
                    for entry in entries:
                        if entry['vendor'] == name:
                            needs_fixing.append({
                                'doc_id': entry['doc_id'],
                                'oib': oib,
                                'current': name,
                                'correct': canonical,
                                'invoice': entry['invoice']
                            })
        else:
            # No canonical name - just list variants
            for name in sorted(unique_names):
                count = sum(1 for e in entries if e['vendor'] == name)
                print(f"      - '{name}' ({count}x)")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY - RECORDS NEEDING FIX")
    print("=" * 70)

    if needs_fixing:
        print(f"\n❌ {len(needs_fixing)} records need vendor name correction:\n")

        for i, fix in enumerate(needs_fixing, 1):
            print(f"{i}. Doc ID: {fix['doc_id']}")
            print(f"   Invoice: {fix['invoice']}")
            print(f"   OIB: {fix['oib']}")
            print(f"   Current: '{fix['current']}'")
            print(f"   Correct: '{fix['correct']}'")
            print()
    else:
        print("\n✅ All vendor names are correct!")

    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
