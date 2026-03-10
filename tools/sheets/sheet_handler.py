"""
Sheet Handler Tool

Helper class to read and write data to Google Sheets.
"""

import logging
import os
from typing import List, Dict, Any, Optional
from tools.google_api_client import create_api_client_auto

logger = logging.getLogger(__name__)

class SheetHandler:
    """
    Handles interactions with Google Sheets API.
    """
    
    def __init__(self):
        self.service = None
        self._initialize_service()

    def _initialize_service(self):
        """Initializes the Sheets API service."""
        try:
            client = create_api_client_auto()
            self.service = client.build('sheets', 'v4')
            logger.info("✅ Sheets API service initialized.")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Sheets API: {e}")
            self.service = None

    def read_sheet_data(self, spreadsheet_id: str, range_name: str) -> List[Dict[str, Any]]:
        """
        Reads data from a sheet and returns it as a list of dictionaries.
        Assumes the first row contains headers.
        """
        if not self.service:
            logger.error("Sheets service not initialized.")
            return []

        try:
            logger.info(f"📖 Reading sheet {spreadsheet_id} range {range_name}...")
            result = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range=range_name
            ).execute()
            
            rows = result.get('values', [])
            
            if not rows:
                logger.warning("⚠️ No data found.")
                return []

            headers = rows[0]
            data = []
            
            for row in rows[1:]:
                # Create dict from headers and row values
                # Handle cases where row might be shorter than headers
                item = {}
                for i, header in enumerate(headers):
                    if i < len(row):
                        item[header] = row[i]
                    else:
                        item[header] = ""
                data.append(item)
                
            logger.info(f"✅ Read {len(data)} rows.")
            return data

        except Exception as e:
            logger.error(f"❌ Error reading sheet: {e}")
            return []

    def write_data(self, spreadsheet_id: str, range_name: str, values: List[List[Any]]):
        """
        Writes raw values to a sheet.
        """
        if not self.service:
            return

        try:
            body = {
                'values': values
            }
            result = self.service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id, range=range_name,
                valueInputOption='RAW', body=body
            ).execute()
            logger.info(f"✅ {result.get('updatedCells')} cells updated.")
        except Exception as e:
            logger.error(f"❌ Error writing to sheet: {e}")

# Global instance
_sheet_handler = SheetHandler()

def get_sheet_handler() -> SheetHandler:
    return _sheet_handler
