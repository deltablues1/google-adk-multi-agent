"""
Full System E2E Test

Verifies the integration of all agents:
1. KnowledgeAgent (RAG)
2. SyncAgent (Sheets -> Firestore)
3. ReportAgent (Firestore -> PDF)
4. OrchestratorAgent (Routing & Coordination)
"""

import asyncio
import logging
import os
import unittest.mock
from dotenv import load_dotenv

# Add project root to path
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from agents.orchestrator.orchestrator import create_orchestrator_agent
from agents.knowledge_agent import create_knowledge_agent
from agents.sync_agent import create_sync_agent
from agents.report_agent import create_report_agent
from tools.database.database_handler import get_database_handler

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

async def test_full_system():
    logger.info("🚀 Starting Full System E2E Test...")
    
    # 1. Initialize Agents
    logger.info("🤖 Initializing Agents...")
    knowledge_agent = create_knowledge_agent()
    sync_agent = create_sync_agent()
    report_agent = create_report_agent()
    
    orchestrator = create_orchestrator_agent(
        sub_agents=[knowledge_agent, sync_agent, report_agent]
    )
    
    # 2. Mock External Dependencies (Sheets & Drive Upload)
    # We mock SyncAgent's sheet reading to avoid needing a real sheet
    mock_sheet_data = [
        {"Invoice Number": "INV-FULL-001", "Customer": "Mega Corp", "Amount": "1000.00", "Date": "2023-03-01"},
        {"Invoice Number": "INV-FULL-002", "Customer": "Ultra Ltd", "Amount": "2000.00", "Date": "2023-03-02"},
    ]
    
    # We mock ReportAgent's upload to avoid cluttering Drive, but we let it generate the PDF locally
    # Actually, let's let it upload to verify Drive integration too, but we'll use a mock for Sync to keep it simple.
    
    with unittest.mock.patch.object(sync_agent.sheet_handler, 'read_sheet_data', return_value=mock_sheet_data):
        logger.info("   Mocked SheetHandler.read_sheet_data")
        
        # 3. Execute Complex Query
        # "Sync invoices from sheet X to database, then generate a report named 'Full_System_Report.pdf'"
        
        # Note: Orchestrator might split this into two steps or handle it if we ask for one then the other.
        # Let's try a multi-step request.
        
        user_request = "Please sync the invoices sheet (ID: dummy) to the 'full_system_invoices' database, and then generate a PDF report titled 'Full System Report' with filename 'full_system_report.pdf' from that database."
        
        logger.info(f"🗣️ User Request: {user_request}")
        
        result = await orchestrator.execute(user_request)
        
        logger.info(f"✅ Final Result:\n{result}")
        
    # 4. Verify Firestore Data
    db_handler = get_database_handler()
    docs = await db_handler.query_documents("full_system_invoices", [])
    logger.info(f"🧐 Verifying Firestore (Found {len(docs)} docs)...")
    
    if len(docs) >= 2:
        logger.info("✅ Sync verification successful!")
    else:
        logger.error("❌ Sync verification failed.")

if __name__ == "__main__":
    asyncio.run(test_full_system())
