"""
Find All Invoice Folders

Searches entire Drive for folders with invoices and shows file counts.

Usage:
    py scripts/find_invoice_folders.py
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


async def search_all_folders_with_invoices(credentials):
    """Search for all folders that might contain invoices"""
    from tools.api_implementations.drive_api import drive_search_files

    print("🔍 Searching entire Drive for folders with 'invoice' in name...")

    # Search for all folders with "invoice" in name (case-insensitive)
    query = "mimeType='application/vnd.google-apps.folder' and trashed=false"
    result = await drive_search_files(credentials, query)
    folders = result.get('files', [])

    # Filter for invoice-related folders
    invoice_folders = []
    for folder in folders:
        name_lower = folder['name'].lower()
        if 'invoice' in name_lower or 'račun' in name_lower or 'racun' in name_lower:
            invoice_folders.append(folder)

    return invoice_folders


async def count_files_in_folder(credentials, folder_id: str):
    """Count files in a folder"""
    from tools.api_implementations.drive_api import drive_search_files

    query = f"'{folder_id}' in parents and trashed=false and mimeType!='application/vnd.google-apps.folder'"
    result = await drive_search_files(credentials, query)
    files = result.get('files', [])

    # Count by type
    types = {}
    for file in files:
        mime = file.get('mimeType', 'unknown')
        if 'image' in mime:
            file_type = 'image'
        elif 'pdf' in mime:
            file_type = 'pdf'
        else:
            file_type = 'other'

        types[file_type] = types.get(file_type, 0) + 1

    return len(files), types


async def get_folder_path(credentials, folder_id: str):
    """Get full path to folder"""
    from tools.api_implementations.drive_api import drive_search_files
    from googleapiclient.discovery import build

    try:
        service = build('drive', 'v3', credentials=credentials)
        folder = service.files().get(fileId=folder_id, fields='id,name,parents').execute()

        path = [folder['name']]
        current = folder

        # Walk up the tree
        while 'parents' in current and current['parents']:
            parent_id = current['parents'][0]
            try:
                parent = service.files().get(fileId=parent_id, fields='id,name,parents').execute()
                path.insert(0, parent['name'])
                current = parent
            except:
                break

        return ' / '.join(path)
    except:
        return "Unknown path"


async def main():
    print("=" * 70)
    print("Find Invoice Folders")
    print("=" * 70)

    from tools.google_api_client import create_api_client_auto

    try:
        client = create_api_client_auto()
        credentials = client.credentials
        print("✅ Credentials loaded\n")
    except Exception as e:
        print(f"❌ Failed to load credentials: {e}")
        return

    # Find all invoice-related folders
    invoice_folders = await search_all_folders_with_invoices(credentials)

    if not invoice_folders:
        print("❌ No invoice folders found on Drive")
        return

    print(f"✅ Found {len(invoice_folders)} invoice-related folder(s)\n")

    # Check each folder
    results = []
    for folder in invoice_folders:
        print(f"📁 Checking: {folder['name']}...")
        file_count, file_types = await count_files_in_folder(credentials, folder['id'])
        path = await get_folder_path(credentials, folder['id'])

        results.append({
            'folder': folder,
            'count': file_count,
            'types': file_types,
            'path': path
        })

        print(f"   Files: {file_count}")
        if file_types:
            print(f"   Types: {file_types}")
        print()

    # Summary
    print("=" * 70)
    print("SUMMARY - Folders with Files")
    print("=" * 70)

    folders_with_files = [r for r in results if r['count'] > 0]
    folders_with_files.sort(key=lambda x: x['count'], reverse=True)

    if not folders_with_files:
        print("\n❌ No folders contain files!")
        print("\n💡 All invoice folders are empty. Please upload documents.")
        return

    print()
    for i, result in enumerate(folders_with_files, 1):
        folder = result['folder']
        count = result['count']
        types = result['types']
        path = result['path']

        print(f"{i}. 📁 {folder['name']}")
        print(f"   Path: {path}")
        print(f"   Folder ID: {folder['id']}")
        print(f"   Files: {count}")
        if types:
            type_str = ', '.join(f"{k}: {v}" for k, v in types.items())
            print(f"   Types: {type_str}")

        # Check if this is the 117 files folder
        if count == 117:
            print(f"   ⭐ THIS IS IT! Your 117 documents are here!")

        print()

    # Instructions
    print("=" * 70)
    print("NEXT STEPS")
    print("=" * 70)

    if any(r['count'] == 117 for r in folders_with_files):
        target = next(r for r in folders_with_files if r['count'] == 117)
        folder_id = target['folder']['id']
        folder_name = target['folder']['name']

        print(f"\n✅ Found your 117 documents in: {folder_name}")
        print(f"   Folder ID: {folder_id}")

        print(f"\n💡 To process these files:")
        print(f"   Option 1: Move them to ADK_Workspace/Invoices_Input/")
        print(f"   Option 2: Process directly from this folder:")
        print(f"             (I can create a custom script for this folder ID)")

        print(f"\n🤔 Which do you prefer?")
    else:
        max_folder = folders_with_files[0]
        print(f"\n📊 Largest folder has {max_folder['count']} files:")
        print(f"   {max_folder['folder']['name']}")
        print(f"   Path: {max_folder['path']}")

        if max_folder['count'] > 50:
            print(f"\n💡 Is this your invoice folder?")
            print(f"   If yes, I can process it directly!")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
