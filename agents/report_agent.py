"""
Report Agent

Generates PDF reports from Firestore data.
"""

import logging
import os
from typing import Dict, Any, List
from agents.base_agent import BaseAgent
from tools.database.database_handler import get_database_handler
from tools.reporting.pdf_generator import get_pdf_generator
from tools.drive_navigator import get_drive_navigator
from tools.api_implementations.drive_api import drive_upload_file
from tools.google_api_client import create_api_client_auto
from google.genai import types

logger = logging.getLogger(__name__)

class ReportAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="report",
            model="publishers/google/models/gemini-2.5-flash",
        )
        self.db_handler = get_database_handler()
        self.pdf_generator = get_pdf_generator()
        self.drive_navigator = None # Lazy load

    async def _get_drive_navigator(self):
        if not self.drive_navigator:
            self.drive_navigator = await get_drive_navigator()
        return self.drive_navigator

    def _load_instructions(self) -> str:
        return """
            You are the Report Agent. Your job is to generate PDF reports based on data in Firestore.
            
            When asked to generate a report:
            1. Query the database for the requested data.
            2. Use `generate_pdf_report` to create the PDF and upload it to Drive.
            
            Always provide the link to the generated report.
            """

    async def generate_pdf_report(self, collection_name: str, report_title: str, filename: str) -> str:
        """
        Tool: Generates a PDF report from a Firestore collection and uploads it to Drive.
        """
        logger.info(f"📄 Generating Report: {report_title} from {collection_name}...")
        
        # 1. Fetch Data
        # query_documents returns List[Dict], so we use it directly
        data = await self.db_handler.query_documents(collection_name, [])
        
        if not data:
            return "No data found in collection."
        
        # 2. Determine Headers (from first item)
        if not data:
             return "No data to report."
        headers = list(data[0].keys())
        
        # 3. Generate PDF
        pdf_path = self.pdf_generator.generate_pdf(filename, report_title, data, headers)
        if not pdf_path:
            return "Failed to generate PDF."
            
        # 4. Upload to Drive
        navigator = await self._get_drive_navigator()
        reports_folder_id = navigator.get_folder_id('reports')
        
        if not reports_folder_id:
            return "Reports folder not found on Drive."
            
        credentials = create_api_client_auto().credentials
        file_id = await drive_upload_file(credentials, pdf_path, filename, mime_type='application/pdf', parent_folder_id=reports_folder_id)
        
        # Cleanup local file
        try:
            os.remove(pdf_path)
        except:
            pass
            
        return f"Report generated successfully! File ID: {file_id}"

    def get_tools(self) -> List[Any]:
        return [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name="generate_pdf_report",
                        description="Generates a PDF report from a Firestore collection.",
                        parameters=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "collection_name": types.Schema(type=types.Type.STRING, description="The Firestore collection to query."),
                                "report_title": types.Schema(type=types.Type.STRING, description="The title of the report."),
                                "filename": types.Schema(type=types.Type.STRING, description="The filename for the PDF (e.g., 'report.pdf').")
                            },
                            required=["collection_name", "report_title", "filename"]
                        )
                    )
                ]
            )
        ]

    async def _execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Any:
        if tool_name == "generate_pdf_report":
            return await self.generate_pdf_report(args["collection_name"], args["report_title"], args["filename"])
        return await super()._execute_tool(tool_name, args)

def create_report_agent():
    return ReportAgent()
