"""
Sync Sheets Workflow

Triggers the Sync Agent to synchronize specific sheets to Firestore.
"""

import asyncio
import logging
import os
from dotenv import load_dotenv
from agents.sync_agent import create_sync_agent

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

async def run_sync_workflow():
    logger.info("🚀 Starting Sync Workflow...")
    
    agent = create_sync_agent()
    
    # Configuration (Could be moved to a config file)
    # Example: Sync "Invoices" sheet
    # We need the Spreadsheet ID. For now, we'll use a placeholder or env var.
    spreadsheet_id = os.getenv('INVOICES_SHEET_ID')
    
    if not spreadsheet_id:
        logger.warning("⚠️ INVOICES_SHEET_ID not set in environment. Skipping sync.")
        return

    result = await agent.sync_sheet_to_db(
        spreadsheet_id=spreadsheet_id,
        range_name="Sheet1!A1:Z", # Adjust range as needed
        collection_name="invoices"
    )
    
    logger.info(f"✅ Workflow Result: {result}")

if __name__ == "__main__":
    asyncio.run(run_sync_workflow())
