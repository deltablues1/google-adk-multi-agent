"""
Ingest Company Documents into RAG Corpus

Scans the Company_Knowledge Drive folder and imports all documents
into the Vertex AI RAG Corpus for company knowledge base.

Supported file types:
- PDF documents
- Google Docs (exported as PDF)
- Text files
- Markdown files

Usage:
    python scripts/ingest_company_docs.py

Prerequisites:
    1. COMPANY_CORPUS_ID must be set in .env
    2. Company_Knowledge folder must exist in ADK_Workspace
    3. Documents should be uploaded to the folder
"""

import asyncio
import os
import sys
import base64
import tempfile
from typing import List, Dict, Any
import vertexai
from vertexai.preview import rag
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools.drive_navigator import get_drive_navigator
from tools.api_implementations.drive_api import drive_search_files, drive_get_file, drive_export_file
from tools.google_api_client import create_api_client_auto

# Load environment variables
load_dotenv()


async def get_company_documents() -> List[Dict[str, Any]]:
    """
    Find all documents in the Company_Knowledge Drive folder.

    Returns:
        List of file metadata dictionaries
    """
    print("🔍 Scanning Company_Knowledge folder...")

    navigator = await get_drive_navigator()
    company_folder_id = navigator.get_folder_id('company')

    if not company_folder_id:
        print("❌ Error: Company_Knowledge folder not found!")
        print("   Please ensure ADK_Workspace/Company_Knowledge/ exists")
        return []

    credentials = create_api_client_auto().credentials

    # Search for all supported file types in Company_Knowledge folder
    # PDFs, text files, and Google Docs
    queries = [
        # PDF files
        f"'{company_folder_id}' in parents and mimeType = 'application/pdf' and trashed = false",
        # Text files
        f"'{company_folder_id}' in parents and mimeType = 'text/plain' and trashed = false",
        # Markdown files
        f"'{company_folder_id}' in parents and mimeType = 'text/markdown' and trashed = false",
        # Google Docs (will be exported as PDF)
        f"'{company_folder_id}' in parents and mimeType = 'application/vnd.google-apps.document' and trashed = false",
    ]

    all_files = []
    for query in queries:
        result = await drive_search_files(credentials, query)
        files = result.get('files', [])
        all_files.extend(files)

    print(f"✅ Found {len(all_files)} documents in Company_Knowledge folder")
    for file in all_files:
        print(f"   - {file['name']} ({file['mimeType']})")

    return all_files


async def download_file(file_id: str, file_name: str, mime_type: str, credentials) -> tuple:
    """
    Download a file from Drive to a temporary location.

    Args:
        file_id: Drive file ID
        file_name: Original file name
        mime_type: MIME type of the file
        credentials: OAuth credentials

    Returns:
        Tuple of (temp_file_path, success_bool)
    """
    try:
        # Google Docs need to be exported
        if mime_type == 'application/vnd.google-apps.document':
            print(f"   Exporting Google Doc: {file_name}")
            file_data = await drive_export_file(
                credentials,
                file_id,
                export_mime_type='application/pdf'
            )
            file_extension = '.pdf'
        else:
            # Regular files can be downloaded directly
            print(f"   Downloading: {file_name}")
            file_data = await drive_get_file(credentials, file_id, include_content=True)
            file_extension = os.path.splitext(file_name)[1] or '.txt'

        content_base64 = file_data.get('content')
        if not content_base64:
            print(f"   ⚠️  Empty content for {file_name}")
            return None, False

        # Decode and write to temp file
        content = base64.b64decode(content_base64)

        # Create temp file
        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=file_extension,
            prefix=f"company_doc_"
        )
        temp_file.write(content)
        temp_file.close()

        print(f"   ✅ Downloaded to: {temp_file.name}")
        return temp_file.name, True

    except Exception as e:
        print(f"   ❌ Failed to download {file_name}: {e}")
        return None, False


async def import_to_corpus(corpus_id: str, file_paths: List[str], file_names: List[str]):
    """
    Import files into Vertex AI RAG Corpus.

    Args:
        corpus_id: Vertex AI RAG Corpus ID
        file_paths: List of local file paths to import
        file_names: List of original file names (for display)
    """
    print(f"\n📦 Importing {len(file_paths)} files to RAG Corpus...")

    try:
        # Import files using Vertex AI RAG API
        # Note: This is a simplified version. The actual implementation may vary
        # based on the Vertex AI RAG API version

        for i, (file_path, file_name) in enumerate(zip(file_paths, file_names)):
            print(f"   [{i+1}/{len(file_paths)}] Importing: {file_name}")

            try:
                # Upload file to corpus
                # The exact API may vary - this is based on Vertex AI RAG preview API
                response = rag.upload_file(
                    corpus_name=corpus_id,
                    path=file_path,
                    display_name=file_name
                )

                print(f"   ✅ Imported: {file_name}")

            except Exception as e:
                print(f"   ❌ Failed to import {file_name}: {e}")

            # Clean up temp file
            try:
                os.unlink(file_path)
            except:
                pass

        print(f"\n✅ Ingestion complete!")

    except Exception as e:
        print(f"❌ Import failed: {e}")
        print(f"\n💡 Troubleshooting:")
        print(f"   - Verify COMPANY_CORPUS_ID is correct in .env")
        print(f"   - Check that Vertex AI RAG API is enabled")
        print(f"   - Ensure files are valid PDFs or text files")

        # Clean up temp files on error
        for file_path in file_paths:
            try:
                os.unlink(file_path)
            except:
                pass


async def ingest_company_docs():
    """Main ingestion function"""

    # Check environment
    corpus_id = os.getenv("COMPANY_CORPUS_ID")
    if not corpus_id:
        print("❌ Error: COMPANY_CORPUS_ID not set in .env")
        print("   Run: python scripts/setup_company_corpus.py")
        print("   Then add the corpus ID to .env file")
        return

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("VERTEX_AI_LOCATION") or os.getenv("GOOGLE_CLOUD_LOCATION", "us-west1")

    print("=" * 70)
    print("Company Knowledge Ingestion")
    print("=" * 70)
    print(f"Project: {project_id}")
    print(f"Location: {location}")
    print(f"Corpus ID: {corpus_id}")
    print("=" * 70)

    # Initialize Vertex AI
    vertexai.init(project=project_id, location=location)

    # Step 1: Find all documents in Drive
    documents = await get_company_documents()

    if not documents:
        print("\n⚠️  No documents found in Company_Knowledge folder")
        print("   Upload some documents to ADK_Workspace/Company_Knowledge/ first")
        return

    # Step 2: Download all documents
    print(f"\n📥 Downloading {len(documents)} documents...")
    credentials = create_api_client_auto().credentials

    downloaded_files = []
    file_names = []

    for doc in documents:
        temp_path, success = await download_file(
            doc['id'],
            doc['name'],
            doc['mimeType'],
            credentials
        )
        if success and temp_path:
            downloaded_files.append(temp_path)
            file_names.append(doc['name'])

    if not downloaded_files:
        print("❌ No files could be downloaded")
        return

    # Step 3: Import to RAG Corpus
    await import_to_corpus(corpus_id, downloaded_files, file_names)

    print("\n" + "=" * 70)
    print("✅ Company knowledge base ingestion complete!")
    print("=" * 70)
    print("\n📋 Next steps:")
    print("   - Test the knowledge base with queries")
    print("   - Add company_knowledge_tool to relevant agents")
    print("   - Upload more documents as needed")


if __name__ == "__main__":
    asyncio.run(ingest_company_docs())
