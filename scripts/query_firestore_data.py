"""
Query Firestore Data

Shows how to query and retrieve data from Firestore collections.

Usage:
    py scripts/query_firestore_data.py
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


async def query_expense_records(limit=5):
    """Query expense records from Firestore"""
    from tools.adk_tools.firestore_adk_tools import query_expenses

    print("📊 Querying expense-records collection...\n")

    # Query all expenses (or filter by category)
    result = await query_expenses(limit=limit)

    if result.get('status') == 'success':
        expenses = result.get('expenses', [])
        print(f"✅ Found {len(expenses)} expense records:\n")

        for i, expense in enumerate(expenses, 1):
            print(f"{i}. {expense.get('vendor', 'Unknown')} - {expense.get('amount', 0)} {expense.get('currency', 'EUR')}")
            print(f"   Date: {expense.get('date', 'N/A')}")
            print(f"   Category: {expense.get('category', 'N/A')}")
            print(f"   Invoice: {expense.get('invoice_number', 'N/A')}")
            if expense.get('items'):
                print(f"   Items: {len(expense['items'])} products")
            print()
    else:
        print(f"❌ Query failed: {result.get('error')}")


async def query_products(limit=10):
    """Query products from Firestore"""
    from tools.adk_tools.firestore_adk_tools import query_products

    print("📦 Querying products collection...\n")

    # Query all products (or filter by supplier)
    result = await query_products(limit=limit)

    if result.get('status') == 'success':
        products = result.get('products', [])
        print(f"✅ Found {len(products)} products:\n")

        for i, product in enumerate(products, 1):
            print(f"{i}. {product.get('name', 'Unknown')} - {product.get('price', 0)} {product.get('currency', 'EUR')}")
            print(f"   Supplier: {product.get('supplier', 'N/A')}")
            print(f"   Category: {product.get('category', 'N/A')}")
            print()
    else:
        print(f"❌ Query failed: {result.get('error')}")


async def query_by_category(category: str):
    """Query expenses by category"""
    from tools.adk_tools.firestore_adk_tools import query_expenses

    print(f"🔍 Querying expenses in category: {category}\n")

    result = await query_expenses(category=category, limit=20)

    if result.get('status') == 'success':
        expenses = result.get('expenses', [])
        total = sum(e.get('amount', 0) for e in expenses)

        print(f"✅ Found {len(expenses)} expenses in '{category}' category")
        print(f"💰 Total amount: {total:.2f} EUR\n")

        for expense in expenses:
            print(f"  - {expense.get('vendor', 'Unknown')}: {expense.get('amount', 0)} EUR on {expense.get('date', 'N/A')}")
    else:
        print(f"❌ Query failed: {result.get('error')}")


async def show_raw_firestore_data():
    """Show raw Firestore data using database handler"""
    from tools.database.database_handler import get_database_handler

    print("🔥 Accessing Firestore directly...\n")

    db = get_database_handler()

    # Get all collections
    try:
        # Query expense-records
        docs = await db.query_documents("expense-records", limit=3)

        print(f"📄 Sample expense-records (first 3):\n")
        for doc in docs:
            print(f"Document ID: {doc.get('_id', 'N/A')}")
            print(f"  Vendor: {doc.get('vendor', 'N/A')}")
            print(f"  Amount: {doc.get('amount', 0)} {doc.get('currency', 'EUR')}")
            print(f"  Date: {doc.get('date', 'N/A')}")
            print(f"  Category: {doc.get('category', 'N/A')}")
            print(f"  Items: {len(doc.get('items', []))} products")
            print()
    except Exception as e:
        print(f"❌ Error: {e}")


async def main():
    print("=" * 70)
    print("Firestore Data Query Tool")
    print("=" * 70)
    print()

    # 1. Query expense records
    await query_expense_records(limit=5)

    print("-" * 70)
    print()

    # 2. Query products
    await query_products(limit=10)

    print("-" * 70)
    print()

    # 3. Query by category
    await query_by_category("Hrana")

    print()
    print("-" * 70)
    print()

    await query_by_category("Ured")

    print()
    print("=" * 70)
    print("✅ Query complete!")
    print("=" * 70)

    print()
    print("💡 Collections in (default) database:")
    print("   - expense-records: Expense tracking data")
    print("   - products: Product catalog")
    print("   - customers: Customer data")
    print("   - quotes: Quote records")
    print()
    print("🔗 View in Google Cloud Console:")
    print("   https://console.cloud.google.com/firestore/databases/(default)/data")
    print()


if __name__ == "__main__":
    asyncio.run(main())
