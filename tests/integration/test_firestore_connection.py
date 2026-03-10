"""
Verify Firestore Connection

Tests the DatabaseHandler by performing CRUD operations on a test collection.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Force Cloud Logging off for this local test
os.environ["USE_CLOUD_LOGGING"] = "false"

from tools.database.database_handler import get_database_handler

async def verify_firestore():
    logger.info("🚀 Starting Firestore Verification...")
    
    try:
        db = get_database_handler()
        
        if not db.client:
            logger.error("❌ Firestore client failed to initialize")
            sys.exit(1)
            
        collection = "adk_test_collection"
        doc_id = "test_doc_1"
        
        # 1. Test Write
        logger.info("1️⃣ Testing Write...")
        data = {
            "message": "Hello Firestore!",
            "timestamp": datetime.utcnow(),
            "status": "testing"
        }
        await db.add_document(collection, data, doc_id=doc_id)
        
        # 2. Test Read
        logger.info("2️⃣ Testing Read...")
        doc = await db.get_document(collection, doc_id)
        if doc and doc['message'] == "Hello Firestore!":
            logger.info(f"   ✅ Read successful: {doc}")
        else:
            logger.error(f"   ❌ Read failed or mismatch: {doc}")
            sys.exit(1)
            
        # 3. Test Query
        logger.info("3️⃣ Testing Query...")
        results = await db.query_documents(collection, [('status', '==', 'testing')])
        if len(results) > 0:
            logger.info(f"   ✅ Query successful: Found {len(results)} docs")
        else:
            logger.error("   ❌ Query failed: No docs found")
            sys.exit(1)
            
        # 4. Test Delete
        logger.info("4️⃣ Testing Delete...")
        success = await db.delete_document(collection, doc_id)
        if success:
            logger.info("   ✅ Delete successful")
        else:
            logger.error("   ❌ Delete failed")
            sys.exit(1)
            
        logger.info("==================================================")
        logger.info("✅ FIRESTORE CONNECTION VERIFIED")
        logger.info("==================================================")
        
    except Exception as e:
        logger.error(f"❌ Verification Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(verify_firestore())
    except KeyboardInterrupt:
        pass
