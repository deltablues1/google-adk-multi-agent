"""
Drive Navigator Tool

Manages the canonical folder structure on Google Drive based on config/drive_map.yaml.
Ensures that the required folders exist and provides their IDs to agents.
"""

import os
import yaml
import logging
from typing import Dict, Optional, Any
from tools.api_implementations.drive_api import (
    drive_search_files,
    drive_create_folder,
    drive_get_file
)
from tools.google_api_client import create_api_client_auto

logger = logging.getLogger(__name__)

class DriveNavigator:
    """
    Manages the ADK Drive folder structure.
    Singleton pattern to cache folder IDs in memory.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DriveNavigator, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self.config_path = os.path.join(os.getcwd(), 'config', 'drive_map.yaml')
        self.config = self._load_config()
        self.folder_cache: Dict[str, str] = {} # alias -> folder_id
        self._initialized = True

    def _load_config(self) -> Dict[str, Any]:
        """Load drive map configuration"""
        if not os.path.exists(self.config_path):
            logger.error(f"Drive map config not found at {self.config_path}")
            return {}
            
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    async def ensure_structure(self) -> Dict[str, str]:
        """
        Verifies that the folder structure exists on Drive.
        Creates missing folders.
        Returns a map of alias -> folder_id.
        """
        logger.info("🔍 Verifying Drive folder structure...")
        
        credentials = create_api_client_auto().credentials
        structure = self.config.get('structure', {})
        root_config = structure.get('root', {})
        
        # 1. Ensure Root Folder
        root_name = root_config.get('name', 'ADK_Workspace')
        root_id = await self._get_or_create_folder(credentials, root_name, parent_id=None)
        
        self.folder_cache['root'] = root_id
        logger.info(f"✅ Root folder '{root_name}' ready (ID: {root_id})")
        
        # 2. Ensure Subfolders
        subfolders = root_config.get('subfolders', [])
        results = {'root': root_id}
        
        for folder in subfolders:
            name = folder['name']
            alias = folder['alias']
            
            folder_id = await self._get_or_create_folder(credentials, name, parent_id=root_id)
            self.folder_cache[alias] = folder_id
            results[alias] = folder_id
            logger.info(f"✅ Subfolder '{name}' ready (ID: {folder_id})")
            
        return results

    async def _get_or_create_folder(self, credentials, name: str, parent_id: Optional[str] = None) -> str:
        """Finds a folder by name/parent, or creates it if missing."""
        
        # Search query
        query = f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        if parent_id:
            query += f" and '{parent_id}' in parents"
            
        result = await drive_search_files(credentials, query)
        files = result.get('files', [])
        
        if files:
            # Folder exists
            return files[0]['id']
        else:
            # Create folder
            logger.info(f"   Creating missing folder: {name}")
            folder = await drive_create_folder(credentials, name, parent_folder_id=parent_id)
            return folder['id']

    def get_folder_id(self, alias: str) -> Optional[str]:
        """Get ID for a known folder alias (e.g., 'invoices_input')"""
        return self.folder_cache.get(alias)

# Global instance
_navigator = DriveNavigator()

async def get_drive_navigator() -> DriveNavigator:
    """Get the global DriveNavigator instance"""
    if not _navigator.folder_cache:
        # Auto-initialize if empty
        await _navigator.ensure_structure()
    return _navigator
