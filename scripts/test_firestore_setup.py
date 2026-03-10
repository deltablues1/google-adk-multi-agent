"""
Test Firestore Database Setup

Validates that Firestore tools are configured correctly and can connect to databases.

Usage:
    py scripts/test_firestore_setup.py
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


def test_environment():
    """Test environment variables"""
    print("=" * 70)
    print("1. Testing Environment Variables")
    print("=" * 70)

    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if project:
        print(f"✅ GOOGLE_CLOUD_PROJECT: {project}")
        return True
    else:
        print(f"❌ GOOGLE_CLOUD_PROJECT not set")
        return False


def test_imports():
    """Test that Firestore tools can be imported"""
    print("\n" + "=" * 70)
    print("2. Testing Firestore Tools Import")
    print("=" * 70)

    try:
        from tools.adk_tools.firestore_adk_tools import (
            add_product,
            query_products,
            add_customer,
            find_customer,
            create_quote,
            add_expense_record,
            query_expenses
        )
        print("✅ All Firestore tools imported successfully")
        print("   Tools available:")
        print("   - add_product, query_products")
        print("   - add_customer, find_customer")
        print("   - create_quote")
        print("   - add_expense_record, query_expenses")
        return True
    except ImportError as e:
        print(f"❌ Failed to import Firestore tools: {e}")
        return False


async def test_database_connection():
    """Test database connection"""
    print("\n" + "=" * 70)
    print("3. Testing Database Connection")
    print("=" * 70)

    try:
        from tools.database.database_handler import get_database_handler

        db = get_database_handler()
        if db and db.client:
            print("✅ Database handler initialized")
            print(f"   Project: {db.client.project}")
            return True
        else:
            print("❌ Database handler failed to initialize")
            return False

    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False


async def test_expense_agent():
    """Test Expense agent with Firestore tools"""
    print("\n" + "=" * 70)
    print("4. Testing Expense Agent Configuration")
    print("=" * 70)

    try:
        from agents.adk_agents.expense_adk import create_expense_agent

        agent = create_expense_agent()
        print(f"✅ Expense agent created: {agent.name}")
        print(f"   Model: {agent.model}")
        print(f"   Tools: {len(agent.tools)}")

        # Check for Firestore tools
        tool_names = [getattr(tool, '__name__', str(tool)) for tool in agent.tools]
        firestore_tools = [name for name in tool_names if 'add_' in name or 'query_' in name or 'find_' in name or 'create_' in name]

        if firestore_tools:
            print(f"✅ Firestore tools found: {len(firestore_tools)}")
            print("   Firestore tools:")
            for tool in firestore_tools:
                print(f"   - {tool}")
            return True
        else:
            print("⚠️  No Firestore tools found in agent")
            return False

    except Exception as e:
        print(f"❌ Failed to create Expense agent: {e}")
        return False


async def test_write_operations():
    """Test actual write operations (OPTIONAL - creates test data)"""
    print("\n" + "=" * 70)
    print("5. Testing Write Operations (Optional)")
    print("=" * 70)

    # Skip if not interactive (e.g., piped input)
    if not sys.stdin.isatty():
        print("⏭️  Skipping write tests (non-interactive mode)")
        return True

    try:
        response = input("Do you want to test write operations? This will create test data in Firestore. (yes/no): ")
    except (EOFError, KeyboardInterrupt):
        print("\n⏭️  Skipping write tests")
        return True

    if response.lower() not in ['yes', 'y']:
        print("⏭️  Skipping write tests")
        return True

    try:
        from tools.adk_tools.firestore_adk_tools import (
            add_product,
            add_customer,
            add_expense_record
        )

        # Test 1: Add product
        print("\n📦 Testing add_product...")
        product_result = await add_product(
            name="Test Product - DELETE ME",
            price=99.99,
            currency="EUR",
            category="Test",
            description="Test product created by test script"
        )

        if product_result.get('status') == 'success':
            print(f"   ✅ Product created: {product_result.get('product_id')}")
            print(f"   Message: {product_result.get('message')}")
        else:
            print(f"   ❌ Failed: {product_result.get('error')}")
            return False

        # Test 2: Add customer
        print("\n👤 Testing add_customer...")
        customer_result = await add_customer(
            name="Test Customer - DELETE ME",
            email="test@delete.me",
            company="Test Company"
        )

        if customer_result.get('status') == 'success':
            print(f"   ✅ Customer created: {customer_result.get('customer_id')}")
            print(f"   Message: {customer_result.get('message')}")
        else:
            print(f"   ❌ Failed: {customer_result.get('error')}")
            return False

        # Test 3: Add expense record
        print("\n💰 Testing add_expense_record...")
        expense_result = await add_expense_record(
            vendor="Test Vendor - DELETE ME",
            amount=123.45,
            currency="EUR",
            date="2025-01-15",
            category="Test",
            invoice_number="TEST-001"
        )

        if expense_result.get('status') == 'success':
            print(f"   ✅ Expense created: {expense_result.get('expense_id')}")
            print(f"   Message: {expense_result.get('message')}")
        else:
            print(f"   ❌ Failed: {expense_result.get('error')}")
            return False

        print("\n✅ All write operations successful!")
        print("\n⚠️  NOTE: Test data was created. Please delete manually:")
        print("   1. Open Firestore Console")
        print("   2. Delete documents with 'DELETE ME' in the name")

        return True

    except Exception as e:
        print(f"❌ Write operations failed: {e}")
        return False


async def main():
    """Run all tests"""
    print("\n" + "=" * 70)
    print("Firestore Database Setup Test")
    print("=" * 70)

    results = []

    # Test 1: Environment
    results.append(test_environment())

    # Test 2: Imports
    results.append(test_imports())

    # Test 3: Database connection
    results.append(await test_database_connection())

    # Test 4: Expense agent
    results.append(await test_expense_agent())

    # Test 5: Write operations (optional)
    results.append(await test_write_operations())

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(results)
    total = len(results)

    if passed == total:
        print(f"\n🎉 All tests passed! ({passed}/{total})")
        print("\n✅ Firestore setup is ready!")
        print("\n📋 Next steps:")
        print("   1. Upload invoices to ADK_Workspace/Invoices_Input/")
        print("   2. Run: py scripts/batch_process_invoices.py")
        print("   3. Check Firestore Console for populated data")
    else:
        print(f"\n⚠️  Some tests failed ({passed}/{total} passed)")
        print("\n💡 Troubleshooting:")
        print("   - Check .env file has GOOGLE_CLOUD_PROJECT")
        print("   - Verify OAuth credentials are valid")
        print("   - Ensure Firestore API is enabled")
        print("   - Check Firestore collections exist")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
