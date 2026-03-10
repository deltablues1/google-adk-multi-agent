"""
Debug Drive Content

Lists files in ADK_Brain to verify visibility.
"""

import asyncio
import logging
import os
from dotenv import load_dotenv
from tools.drive_navigator import get_drive_navigator
from tools.api_implementations.drive_api import drive_search_files
from tools.google_api_client import create_api_client_auto

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

async def debug_drive():
    logger.info("🔍 Debugging Drive Content...")
    
    try:
        navigator = await get_drive_navigator()
        brain_id = navigator.get_folder_id('brain')
        
        if not brain_id:
            logger.error("❌ ADK_Brain folder NOT found in DriveNavigator cache/lookup.")
            return
            
        logger.info(f"✅ ADK_Brain Folder ID: {brain_id}")
        
        credentials = create_api_client_auto().credentials
        
        # List files in Brain
        query = f"'{brain_id}' in parents and trashed = false"
        logger.info(f"   Executing query: {query}")
        
        result = await drive_search_files(credentials, query)
        files = result.get('files', [])
        
        logger.info(f"📂 Found {len(files)} files in ADK_Brain:")
        for f in files:
            logger.info(f"   - {f['name']} (ID: {f['id']}, Mime: {f['mimeType']})")
            
    except Exception as e:
        logger.error(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(debug_drive())
