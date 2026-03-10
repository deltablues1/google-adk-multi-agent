"""
Ingestion Pipeline

Watches the 'ADK_Brain' folder on Drive.
Reads new files, generates embeddings, and stores them in Firestore.
"""

import logging
import io
from typing import List, Dict, Any
from pypdf import PdfReader
from tools.drive_navigator import get_drive_navigator
from tools.api_implementations.drive_api import drive_get_file, drive_search_files
from tools.knowledge.vector_handler import get_vector_handler
from tools.database.database_handler import get_database_handler
from tools.google_api_client import create_api_client_auto
from google.cloud.firestore_v1.vector import Vector

logger = logging.getLogger(__name__)

class IngestionPipeline:
    """
    Orchestrates the RAG ingestion process.
    """
    
    def __init__(self):
        self.vector_handler = get_vector_handler()
        self.db_handler = get_database_handler()
        self.collection_name = "knowledge_base"

    async def run_ingestion(self):
        """
        Main entry point. Scans ADK_Brain for unindexed files.
        """
        logger.info("🧠 Starting Knowledge Ingestion...")
        
        navigator = await get_drive_navigator()
        brain_id = navigator.get_folder_id('brain')
        
        if not brain_id:
            logger.error("❌ ADK_Brain folder not found!")
            return

        credentials = create_api_client_auto().credentials
        
        # Find all PDFs in Brain folder
        query = f"'{brain_id}' in parents and mimeType = 'application/pdf' and trashed = false"
        result = await drive_search_files(credentials, query)
        files = result.get('files', [])
        
        logger.info(f"Found {len(files)} PDFs in Brain folder.")
        
        for file in files:
            await self.process_file(file['id'], file['name'], file.get('modifiedTime'), credentials)

    async def process_file(self, file_id: str, file_name: str, modified_time: str, credentials):
        """
        Process a single file: Download -> Extract -> Embed -> Store
        Handles updates by checking modifiedTime.
        """
        # Check if already indexed
        existing_docs = await self.db_handler.query_documents(
            self.collection_name, 
            [('source_file_id', '==', file_id)],
            limit=1
        )
        
        if existing_docs:
            existing_doc = existing_docs[0]
            stored_time = existing_doc.get('source_modified_time')
            
            # If stored time matches drive time, skip
            if stored_time == modified_time:
                logger.info(f"⏭️ Skipping {file_name} (Already up to date)")
                return
            
            # If times differ, it's an update!
            logger.info(f"🔄 Update detected for {file_name}!")
            logger.info(f"   Old time: {stored_time}")
            logger.info(f"   New time: {modified_time}")
            
            # Delete old chunks
            await self.db_handler.delete_documents_by_field(self.collection_name, 'source_file_id', file_id)
            logger.info(f"   Deleted old chunks for {file_name}")
            
            # Proceed to re-ingest...

        logger.info(f"📥 Processing {file_name}...")
        
        # 1. Download
        file_data = await drive_get_file(credentials, file_id, include_content=True)
        content_base64 = file_data.get('content')
        
        if not content_base64:
            logger.warning(f"⚠️ Empty content for {file_name}")
            return

        # 2. Extract Text
        import base64
        pdf_bytes = base64.b64decode(content_base64)
        pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
        
        full_text = ""
        for page in pdf_reader.pages:
            full_text += page.extract_text() + "\n"
            
        # 3. Chunk
        chunks = self.vector_handler.chunk_text(full_text)
        logger.info(f"   Split into {len(chunks)} chunks.")
        
        # 4. Embed & Store
        for i, chunk in enumerate(chunks):
            embedding = await self.vector_handler.generate_embedding(chunk)
            
            doc_data = {
                "content": chunk,
                "embedding": Vector(embedding),
                "source_file_id": file_id,
                "source_file_name": file_name,
                "source_modified_time": modified_time,
                "chunk_index": i,
                "created_at": None # Will be set by DB handler
            }
            
            await self.db_handler.add_document(self.collection_name, doc_data)
            
        logger.info(f"✅ Indexed {file_name} successfully.")

# Global instance
_pipeline = IngestionPipeline()

def get_ingestion_pipeline() -> IngestionPipeline:
    return _pipeline
