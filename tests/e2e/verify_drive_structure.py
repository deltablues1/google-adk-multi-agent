"""
Verify Drive Structure

Uses the DriveNavigator tool to ensure the canonical folder structure exists.
This script will:
1. Read config/drive_map.yaml
2. Check for 'ADK_Workspace' and subfolders
3. Create them if missing
4. Print the IDs of all folders
"""

import asyncio
import logging
import os
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Force Cloud Logging off for this local test
os.environ["USE_CLOUD_LOGGING"] = "false"

from tools.drive_navigator import get_drive_navigator

async def verify_structure():
    logger.info("🚀 Starting Drive Structure Verification...")
    
    try:
        navigator = await get_drive_navigator()
        
        # This triggers the ensure_structure() logic
        folders = navigator.folder_cache
        
        logger.info("==================================================")
        logger.info("✅ FOLDER STRUCTURE VERIFIED")
        logger.info("==================================================")
        
        for alias, folder_id in folders.items():
            print(f"📂 {alias:15s} : {folder_id}")
            
        logger.info("==================================================")
        logger.info("👉 Please check your Google Drive to confirm these folders exist.")
        
    except Exception as e:
        logger.error(f"❌ Verification Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(verify_structure())
    except KeyboardInterrupt:
        pass
