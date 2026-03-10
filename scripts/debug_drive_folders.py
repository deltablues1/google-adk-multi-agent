
"""
Debug Drive Folders

Checks if ADK_Workspace and Invoices_Input folders exist and lists files.

Usage:
    py scripts/debug_drive_folders.py
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Fix encoding on Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Load environment
load_dotenv()


async def search_folder(credentials, folder_name: str, parent_id: str = None):
    """Search for a folder by name"""
    from tools.api_implementations.drive_api import drive_search_files

    if parent_id:
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed=false"
    else:
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"

    result = await drive_search_files(credentials, query)
    return result.get('files', [])


async def list_files_in_folder(credentials, folder_id: str):
    """List all files in a folder"""
    from tools.api_implementations.drive_api import drive_search_files

    # All files (not folders)
    query = f"'{folder_id}' in parents and trashed=false"
    result = await drive_search_files(credentials, query)
    return result.get('files', [])


async def main():
    print("=" * 70)
    print("Drive Folders Debug")
    print("=" * 70)

    from tools.google_api_client import create_api_client_auto

    try:
        client = create_api_client_auto()
        credentials = client.credentials
        print("✅ Credentials loaded")
    except Exception as e:
        print(f"❌ Failed to load credentials: {e}")
        return

    # Step 1: Search for ADK_Workspace folder
    print("\n" + "=" * 70)
    print("Step 1: Searching for ADK_Workspace folder")
    print("=" * 70)

    workspace_folders = await search_folder(credentials, "ADK_Workspace")

    if not workspace_folders:
        print("❌ ADK_Workspace folder not found!")
        print("\n💡 Create it manually:")
        print("   1. Go to Google Drive")
        print("   2. Create folder: ADK_Workspace")
        print("   3. Inside it, create: Invoices_Input")
        print("   4. Upload your 117 documents to Invoices_Input")
        return

    print(f"✅ Found {len(workspace_folders)} folder(s) named 'ADK_Workspace':")
    for i, folder in enumerate(workspace_folders, 1):
        print(f"   {i}. ID: {folder['id']}")
        print(f"      Name: {folder['name']}")

    # Use first one
    workspace_id = workspace_folders[0]['id']
    print(f"\n📁 Using workspace folder: {workspace_id}")

    # Step 2: Search for Invoices_Input inside ADK_Workspace
    print("\n" + "=" * 70)
    print("Step 2: Searching for Invoices_Input folder")
    print("=" * 70)

    invoice_folders = await search_folder(credentials, "Invoices_Input", workspace_id)

    if not invoice_folders:
        print("❌ Invoices_Input folder not found inside ADK_Workspace!")
        print("\n💡 Create it:")
        print("   1. Open ADK_Workspace folder in Drive")
        print("   2. Create folder: Invoices_Input")
        print("   3. Upload your 117 documents there")
        return

    print(f"✅ Found {len(invoice_folders)} folder(s) named 'Invoices_Input':")
    for i, folder in enumerate(invoice_folders, 1):
        print(f"   {i}. ID: {folder['id']}")
        print(f"      Name: {folder['name']}")

    # Use first one
    invoices_id = invoice_folders[0]['id']
    print(f"\n📁 Using invoices folder: {invoices_id}")

    # Step 3: List files in Invoices_Input
    print("\n" + "=" * 70)
    print("Step 3: Listing files in Invoices_Input")
    print("=" * 70)

    files = await list_files_in_folder(credentials, invoices_id)

    print(f"\n📋 Found {len(files)} file(s):")

    if len(files) == 0:
        print("❌ No files found!")
        print("\n💡 Upload your documents:")
        print("   1. Open Invoices_Input folder in Drive")
        print("   2. Upload all 117 invoice documents")
        return

    # Group by type
    file_types = {}
    for file in files:
        mime = file.get('mimeType', 'unknown')
        file_types[mime] = file_types.get(mime, 0) + 1

    print("\n📊 File types:")
    for mime, count in file_types.items():
        mime_display = mime.split('/')[-1] if '/' in mime else mime
        print(f"   - {mime_display}: {count} file(s)")

    # Show first 10 files
    print(f"\n📄 First 10 files:")
    for i, file in enumerate(files[:10], 1):
        print(f"   {i}. {file['name']} ({file.get('mimeType', 'unknown').split('/')[-1]})")

    if len(files) > 10:
        print(f"   ... and {len(files) - 10} more files")

    # Step 4: Check DriveNavigator
    print("\n" + "=" * 70)
    print("Step 4: Checking DriveNavigator")
    print("=" * 70)

    try:
        from tools.drive_navigator import get_drive_navigator

        navigator = await get_drive_navigator()
        folder_id = navigator.get_folder_id('invoices_input')

        if folder_id:
            print(f"✅ DriveNavigator can access 'invoices_input'")
            print(f"   Folder ID: {folder_id}")

            if folder_id == invoices_id:
                print(f"   ✅ ID matches! Everything is correct.")
            else:
                print(f"   ⚠️  ID mismatch!")
                print(f"   Expected: {invoices_id}")
                print(f"   Got: {folder_id}")
        else:
            print(f"❌ DriveNavigator cannot find 'invoices_input' alias")
            print(f"   This is the problem!")

    except Exception as e:
        print(f"❌ DriveNavigator error: {e}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    if len(files) > 0:
        print(f"\n✅ Everything looks good!")
        print(f"   - ADK_Workspace folder: {workspace_id}")
        print(f"   - Invoices_Input folder: {invoices_id}")
        print(f"   - Files found: {len(files)}")

        print(f"\n💡 Try batch processing now:")
        print(f"   py scripts/batch_process_invoices.py")
    else:
        print(f"\n⚠️  Folders exist but no files found")
        print(f"   Please upload your 117 documents to:")
        print(f"   ADK_Workspace/Invoices_Input/")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
