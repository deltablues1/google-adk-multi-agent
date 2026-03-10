"""
Test Firestore Connection

Verifies Firestore connectivity and creates necessary collections.
"""

import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

# Load environment
load_dotenv()


def test_firestore_connection():
    """Test Firestore connection"""
    print("=" * 80)
    print("TEST: Firestore Connection")
    print("=" * 80)

    # Check environment variables
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    print(f"\n1. Environment Configuration:")
    print(f"   Project ID: {project_id}")
    print(f"   Credentials: {credentials_path}")

    if not project_id:
        print("\n[FAIL] GOOGLE_CLOUD_PROJECT not set in .env")
        return False

    if not os.path.exists(credentials_path):
        print(f"\n[FAIL] Credentials file not found: {credentials_path}")
        return False

    print("   [OK] Environment variables configured")

    # Try to import Firestore
    print("\n2. Importing Firestore library...")
    try:
        from google.cloud import firestore
        print("   [OK] Firestore library available")
    except ImportError as e:
        print(f"   [FAIL] Firestore library not available: {e}")
        print("   Install with: pip install google-cloud-firestore")
        return False

    # Try to initialize Firestore client
    print("\n3. Initializing Firestore client...")
    try:
        db = firestore.Client(project=project_id)
        print(f"   [OK] Firestore client initialized")
        print(f"   Project: {db.project}")
    except Exception as e:
        print(f"   [FAIL] Could not initialize Firestore: {e}")
        return False

    # Test write operation (create test document)
    print("\n4. Testing write operation...")
    try:
        test_ref = db.collection("_connection_test").document("test_doc")
        test_ref.set({
            "test": True,
            "timestamp": firestore.SERVER_TIMESTAMP,
            "message": "Connection test successful"
        })
        print("   [OK] Write operation successful")
    except Exception as e:
        print(f"   [FAIL] Write operation failed: {e}")
        return False

    # Test read operation
    print("\n5. Testing read operation...")
    try:
        doc = test_ref.get()
        if doc.exists:
            data = doc.to_dict()
            print("   [OK] Read operation successful")
            print(f"   Document data: {data}")
        else:
            print("   [FAIL] Document not found")
            return False
    except Exception as e:
        print(f"   [FAIL] Read operation failed: {e}")
        return False

    # Clean up test document
    print("\n6. Cleaning up test document...")
    try:
        test_ref.delete()
        print("   [OK] Test document deleted")
    except Exception as e:
        print(f"   [WARN] Could not delete test document: {e}")

    # Check if fiscalization collections exist
    print("\n7. Checking fiscalization collections...")
    collections_to_check = [
        "fiscalization_ledger",
        "fiscalization_retry_queue",
        "fiscalization_audit"
    ]

    for collection_name in collections_to_check:
        try:
            # Check if collection has any documents
            docs = db.collection(collection_name).limit(1).stream()
            has_docs = False
            for doc in docs:
                has_docs = True
                break

            if has_docs:
                print(f"   [OK] Collection '{collection_name}' exists with documents")
            else:
                print(f"   [INFO] Collection '{collection_name}' exists but is empty")
        except Exception as e:
            print(f"   [INFO] Collection '{collection_name}' will be created on first write")

    print("\n" + "=" * 80)
    print("[SUCCESS] Firestore Connection Test Passed!")
    print("=" * 80)

    print("\nFirestore is ready for:")
    print("  - fiscalization_ledger (invoice persistence)")
    print("  - fiscalization_retry_queue (48h retry queue)")
    print("  - fiscalization_audit (audit trail)")

    return True


if __name__ == "__main__":
    success = test_firestore_connection()
    sys.exit(0 if success else 1)
