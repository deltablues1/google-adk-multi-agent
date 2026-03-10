"""
Verify Smart Knowledge Update

Tests the "Delete & Re-learn" logic:
1. Simulates ingesting a file (Version 1).
2. Simulates updating the file (Version 2) with a newer modifiedTime.
3. Verifies that old chunks are deleted and new ones are added.
"""

import asyncio
import logging
import os
import unittest.mock
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Add project root to path
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from tools.knowledge.ingestion_pipeline import get_ingestion_pipeline
from tools.database.database_handler import get_database_handler

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

async def verify_smart_update():
    logger.info("🚀 Starting Smart Update Verification...")
    
    pipeline = get_ingestion_pipeline()
    db_handler = get_database_handler()
    
    # Mock data
    file_id = "mock_file_123"
    file_name = "smart_update_test.pdf"
    
    # 1. Simulate Initial Ingestion (Version 1)
    logger.info("\n--- Step 1: Initial Ingestion (Version 1) ---")
    time_v1 = "2023-01-01T12:00:00.000Z"
    
    # Mock drive_get_file to return content
    # We mock the entire process_file to control the flow better, 
    # OR we mock the dependencies inside it. Let's mock dependencies.
    
    # Mock PdfReader to avoid parsing invalid PDF data
    mock_pdf_page = unittest.mock.Mock()
    mock_pdf_page.extract_text.return_value = "Mock PDF Content"
    mock_pdf_reader = unittest.mock.Mock()
    mock_pdf_reader.pages = [mock_pdf_page]

    # Mock VectorHandler to return dummy embeddings
    with unittest.mock.patch('tools.knowledge.vector_handler.VectorHandler.generate_embedding', return_value=[0.1]*768), \
         unittest.mock.patch('tools.knowledge.vector_handler.VectorHandler.chunk_text', return_value=["Chunk 1 (V1)", "Chunk 2 (V1)"]), \
         unittest.mock.patch('tools.knowledge.ingestion_pipeline.drive_get_file', return_value={'content': 'SGVsbG8gV29ybGQ='}), \
         unittest.mock.patch('tools.knowledge.ingestion_pipeline.PdfReader', return_value=mock_pdf_reader):
         
        # Run process_file directly
        await pipeline.process_file(file_id, file_name, time_v1, None)
        
    # Verify V1 is in DB
    docs_v1 = await db_handler.query_documents("knowledge_base", [('source_file_id', '==', file_id)])
    logger.info(f"   V1 Docs count: {len(docs_v1)}")
    if len(docs_v1) == 2 and docs_v1[0]['source_modified_time'] == time_v1:
        logger.info("✅ V1 Ingestion Successful")
    else:
        logger.error("❌ V1 Ingestion Failed")
        return

    # 2. Simulate Update (Version 2)
    logger.info("\n--- Step 2: Update (Version 2) ---")
    time_v2 = "2023-01-02T12:00:00.000Z" # Newer time
    
    # Mock with NEW content
    with unittest.mock.patch('tools.knowledge.vector_handler.VectorHandler.generate_embedding', return_value=[0.2]*768), \
         unittest.mock.patch('tools.knowledge.vector_handler.VectorHandler.chunk_text', return_value=["Chunk 1 (V2)", "Chunk 2 (V2)", "Chunk 3 (V2)"]), \
         unittest.mock.patch('tools.knowledge.ingestion_pipeline.drive_get_file', return_value={'content': 'SGVsbG8gV29ybGQ='}), \
         unittest.mock.patch('tools.knowledge.ingestion_pipeline.PdfReader', return_value=mock_pdf_reader):
         
        # Run process_file again with newer time
        await pipeline.process_file(file_id, file_name, time_v2, None)
        
    # Verify V2 is in DB (and V1 is gone)
    docs_v2 = await db_handler.query_documents("knowledge_base", [('source_file_id', '==', file_id)])
    logger.info(f"   V2 Docs count: {len(docs_v2)}")
    
    v1_chunks = [d for d in docs_v2 if d['source_modified_time'] == time_v1]
    v2_chunks = [d for d in docs_v2 if d['source_modified_time'] == time_v2]
    
    if len(v1_chunks) == 0 and len(v2_chunks) == 3:
        logger.info("✅ Smart Update Successful! (Old chunks deleted, new ones added)")
    else:
        logger.error(f"❌ Smart Update Failed. V1 chunks: {len(v1_chunks)}, V2 chunks: {len(v2_chunks)}")

    # Cleanup
    await db_handler.delete_documents_by_field("knowledge_base", "source_file_id", file_id)

if __name__ == "__main__":
    asyncio.run(verify_smart_update())
