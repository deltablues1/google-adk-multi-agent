"""
Sync Agent

Synchronizes data from Google Sheets to Firestore.
"""

import logging
from typing import Dict, Any, List
from agents.base_agent import BaseAgent
from tools.sheets.sheet_handler import get_sheet_handler
from tools.database.database_handler import get_database_handler
from google.genai import types

logger = logging.getLogger(__name__)

class SyncAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="sync",
            model="publishers/google/models/gemini-2.5-flash",
        )
        self.sheet_handler = get_sheet_handler()
        self.db_handler = get_database_handler()

    def _load_instructions(self) -> str:
        return """
            You are the Sync Agent. Your job is to synchronize data from Google Sheets to the Firestore database.
            
            When asked to sync a sheet:
            1. Use `read_sheet_data` to get the data.
            2. Use `update_firestore_collection` to save it to the database.
            
            IMPORTANT: If the user request contains multiple tasks (e.g., "Sync and then generate report"), IGNORE the other tasks. 
            FOCUS ONLY ON SYNCING THE SHEET. Do not comment on tasks you cannot perform.
            
            Always confirm when the sync is complete and how many records were processed.
            """

    async def sync_sheet_to_db(self, spreadsheet_id: str, range_name: str, collection_name: str) -> str:
        """
        Tool: Reads a sheet and updates a Firestore collection.
        """
        logger.info(f"🔄 Syncing Sheet ({spreadsheet_id}) to Collection ({collection_name})...")
        
        # 1. Read Data
        data = self.sheet_handler.read_sheet_data(spreadsheet_id, range_name)
        if not data:
            return "No data found in sheet."
            
        logger.info(f"   Read {len(data)} rows.")
        
        # 2. Write to Firestore
        count = 0
        for item in data:
            # Use a unique ID if available, otherwise auto-generate
            doc_id = item.get('ID') or item.get('id') or item.get('Invoice Number')
            
            if doc_id:
                await self.db_handler.add_document(collection_name, item, doc_id=str(doc_id))
            else:
                await self.db_handler.add_document(collection_name, item)
            count += 1
            
        return f"Successfully synced {count} records to '{collection_name}'."

    def get_tools(self) -> List[Any]:
        return [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name="sync_sheet_to_db",
                        description="Synchronizes a Google Sheet to a Firestore collection.",
                        parameters=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "spreadsheet_id": types.Schema(type=types.Type.STRING, description="The ID of the Google Sheet."),
                                "range_name": types.Schema(type=types.Type.STRING, description="The range to read (e.g., 'Sheet1!A1:Z')."),
                                "collection_name": types.Schema(type=types.Type.STRING, description="The target Firestore collection name.")
                            },
                            required=["spreadsheet_id", "range_name", "collection_name"]
                        )
                    )
                ]
            )
        ]

    async def _execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Any:
        if tool_name == "sync_sheet_to_db":
            return await self.sync_sheet_to_db(args["spreadsheet_id"], args["range_name"], args["collection_name"])
        return await super()._execute_tool(tool_name, args)

def create_sync_agent():
    return SyncAgent()
