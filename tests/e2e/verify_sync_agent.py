import asyncio
import logging
import unittest.mock
from dotenv import load_dotenv
from agents.sync_agent import create_sync_agent
from tools.database.database_handler import get_database_handler

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

async def verify_sync_agent():
    logger.info("🧪 Verifying Sync Agent...")
    
    # 1. Mock SheetHandler
    agent = create_sync_agent()
    
    mock_data = [
        {"Invoice Number": "INV-100", "Customer": "Mock Corp", "Amount": "500.00", "Date": "2023-02-01"},
        {"Invoice Number": "INV-101", "Customer": "Test Ltd", "Amount": "750.00", "Date": "2023-02-02"},
    ]
    
    # Patch the read_sheet_data method on the instance's sheet_handler
    with unittest.mock.patch.object(agent.sheet_handler, 'read_sheet_data', return_value=mock_data):
        logger.info("   Mocked SheetHandler.read_sheet_data")
        
        # 2. Run Sync
        spreadsheet_id = "dummy_sheet_id"
        range_name = "Sheet1!A1:Z"
        collection_name = "test_synced_invoices"
        
        logger.info(f"🚀 Syncing to '{collection_name}'...")
        result = await agent.sync_sheet_to_db(spreadsheet_id, range_name, collection_name)
        
        logger.info(f"✅ Result: {result}")
        
    # 3. Verify Data in Firestore
    db_handler = get_database_handler()
    docs = await db_handler.query_documents(collection_name, [])
    
    logger.info(f"🧐 Verifying Firestore content (Found {len(docs)} docs)...")
    found_inv_100 = False
    for doc in docs:
        if doc.get("Invoice Number") == "INV-100":
            found_inv_100 = True
            logger.info("   Found INV-100!")
            
    if found_inv_100:
        logger.info("✅ Sync verification successful!")
    else:
        logger.error("❌ Sync verification failed: INV-100 not found.")

if __name__ == "__main__":
    asyncio.run(verify_sync_agent())
