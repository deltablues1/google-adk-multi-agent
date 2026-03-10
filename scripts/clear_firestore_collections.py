"""
Clear Firestore Collections

Deletes all documents from specified Firestore collections.
Use this to reset databases before re-processing invoices.

CAUTION: This will permanently delete all data!

Usage:
    py scripts/clear_firestore_collections.py
"""

import asyncio
import os
import sys
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


async def clear_collection(collection_name: str, batch_size: int = 100) -> int:
    """Delete all documents from a collection"""
    from tools.database.database_handler import get_database_handler

    db = get_database_handler()

    print(f"\n🗑️  Clearing collection: {collection_name}")

    try:
        # Get all documents
        docs = await db.query_documents(collection_name, filters=[], limit=1000)

        if not docs:
            print(f"   ℹ️  Collection is already empty")
            return 0

        print(f"   Found {len(docs)} documents to delete...")

        # Delete in batches
        deleted_count = 0
        for doc in docs:
            doc_id = doc.get('_id')
            if doc_id:
                await db.delete_document(collection_name, doc_id)
                deleted_count += 1

                if deleted_count % 10 == 0:
                    print(f"   Deleted {deleted_count}/{len(docs)}...")

        print(f"   ✅ Deleted {deleted_count} documents from '{collection_name}'")
        return deleted_count

    except Exception as e:
        print(f"   ❌ Error clearing collection: {e}")
        return 0


async def main():
    print("=" * 70)
    print("Firestore Collections Cleanup")
    print("=" * 70)

    print("\n⚠️  WARNING: This will permanently delete all data!")
    print("\nCollections to be cleared:")
    print("   - expense-records")
    print("   - products")
    print("   - customers")
    print("   - quotes")

    # Safety confirmation
    response = input("\n❓ Are you sure you want to proceed? (yes/no): ")

    if response.lower() != 'yes':
        print("\n❌ Cancelled. No data was deleted.")
        return

    print("\n🚀 Starting cleanup...")

    # Clear collections
    collections = ['expense-records', 'products', 'customers', 'quotes']
    total_deleted = 0

    for collection in collections:
        deleted = await clear_collection(collection)
        total_deleted += deleted

    # Summary
    print("\n" + "=" * 70)
    print("CLEANUP SUMMARY")
    print("=" * 70)
    print(f"\n✅ Total documents deleted: {total_deleted}")
    print(f"📊 Collections cleared: {len(collections)}")

    print("\n💡 Firestore is now clean and ready for fresh data!")
    print("\n📋 Next steps:")
    print("   1. Run batch_process_invoices.py to populate databases")
    print("   2. Data will be saved to both Firestore and Google Sheets")
    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
