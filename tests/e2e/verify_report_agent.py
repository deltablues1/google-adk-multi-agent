import asyncio
import logging
import os
from dotenv import load_dotenv
from agents.report_agent import create_report_agent
from tools.database.database_handler import get_database_handler

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

async def verify_report_agent():
    logger.info("🧪 Verifying Report Agent...")
    
    # 1. Setup Dummy Data in Firestore
    db_handler = get_database_handler()
    collection_name = "test_invoices"
    
    test_data = [
        {"Invoice Number": "INV-001", "Customer": "Alice", "Amount": "100.00", "Date": "2023-01-01"},
        {"Invoice Number": "INV-002", "Customer": "Bob", "Amount": "250.50", "Date": "2023-01-02"},
        {"Invoice Number": "INV-003", "Customer": "Charlie", "Amount": "50.00", "Date": "2023-01-03"},
    ]
    
    logger.info(f"📝 Seeding '{collection_name}' with {len(test_data)} documents...")
    for item in test_data:
        await db_handler.add_document(collection_name, item, doc_id=item["Invoice Number"])
        
    # 2. Run Report Agent
    agent = create_report_agent()
    report_title = "Test Invoice Report"
    filename = "test_report.pdf"
    
    logger.info("🚀 Generating Report...")
    result = await agent.generate_pdf_report(
        collection_name=collection_name,
        report_title=report_title,
        filename=filename
    )
    
    logger.info(f"✅ Result: {result}")
    
    # 3. Cleanup (Optional: Delete test collection)
    # For now, we keep it to verify manually in console if needed.

if __name__ == "__main__":
    asyncio.run(verify_report_agent())
