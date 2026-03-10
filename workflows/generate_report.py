"""
Generate Report Workflow

Triggers the Report Agent to generate a PDF report.
"""

import asyncio
import logging
from dotenv import load_dotenv
from agents.report_agent import create_report_agent

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

async def run_report_workflow():
    logger.info("🚀 Starting Report Workflow...")
    
    agent = create_report_agent()
    
    # Example: Generate Invoice Report
    result = await agent.generate_pdf_report(
        collection_name="invoices",
        report_title="Monthly Invoices Report",
        filename="invoices_report.pdf"
    )
    
    logger.info(f"✅ Workflow Result: {result}")

if __name__ == "__main__":
    asyncio.run(run_report_workflow())
