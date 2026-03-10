"""
Process Specific Receipt Script
Target: smit.bmp in 'Računi OCR'
"""

import asyncio
import logging
import sys
import os
import json

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from config.agent_registry import create_agent_instance
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

FILENAME = "smit.bmp"
FOLDER_OCR = "Računi OCR"
SHEET_NAME = "Ulazni računi 2025"

async def process_receipt():
    logger.info(f"Starting processing for '{FILENAME}'...")
    
    # 1. Initialize Agent
    agent = create_agent_instance("expense")
    logger.info("Expense Agent initialized.")

    # 2. Find the file
    find_prompt = (
        "1. Find the file 'smit.bmp'. First check folder 'Računi OCR' (ID: '1m60DW8mFYBNbuEiwN0J-FJCMzDl3G4bf').\n"
        "   If NOT found there, check folder 'Ulazni računi' (ID: '1LQ82uvlcrZXI5wEmqmvLI0vUPk7wAGMa').\n"
        "   If found in 'Ulazni računi', MOVE IT BACK to 'Računi OCR' first.\n"
        "2. Get the File ID of 'smit.bmp' (which should now be in 'Računi OCR').\n"
        "3. Call 'extract_receipt_data' with the File ID (do NOT download the content yourself).\n"
        "4. Find the folder 'Ulazni računi' to get its ID (if you don't have it).\n"
        f"5. Read the existing data from '{SHEET_NAME}' (ID: '1GtP3gWNXpJc3DOazHDMmFHskF_sM1JeaEJNV6itB2Ik') using 'sheets_get_values' (range 'A:H').\n"
        "6. Check if the receipt is already in the sheet. Compare 'Invoice Number' (if available) or 'Merchant' + 'Date' + 'Amount'.\n"
        "   - If it exists: Log 'Duplicate receipt detected' and STOP. Do NOT append.\n"
        "   - If it does NOT exist: Append the data to '{SHEET_NAME}'.\n"
        "     IMPORTANT: You MUST format the 'values' argument as a LIST OF LISTS, e.g., [[val1, val2, val3]].\n"
        "     Columns Mapping (A-H):\n"
        "     A: RedBr (Leave empty or '1')\n"
        "     B: BrojRacuna (Invoice Number)\n"
        "     C: Datum (Date)\n"
        "     D: Dobavljac (Merchant)\n"
        "     E: OIB (Tax ID)\n"
        "     F: Osnovica (Tax Base)\n"
        "     G: PDV (Tax Amount)\n"
        "     H: Ukupno (Total Amount)\n"
        "7. Move the file to the 'Ulazni računi' folder."
    )
    
    logger.info(f"Sending request to agent: {find_prompt}")
    response = await agent.run(find_prompt)
    
    logger.info("Agent response:")
    print(response)

if __name__ == "__main__":
    asyncio.run(process_receipt())
