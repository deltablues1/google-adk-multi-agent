"""
Find All Large Folders

Finds all folders with many files (potential invoice locations).

Usage:
    py scripts/find_all_large_folders.py
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


async def find_large_folders(credentials, min_files=10):
    """Find all folders with many files"""
    from tools.api_implementations.drive_api import drive_search_files
    from googleapiclient.discovery import build

    print(f"🔍 Searching for folders with at least {min_files} files...")
    print("   (This may take a minute...)\n")

    service = build('drive', 'v3', credentials=credentials)

    # Get all folders
    query = "mimeType='application/vnd.google-apps.folder' and trashed=false"
    result = await drive_search_files(credentials, query)
    all_folders = result.get('files', [])

    print(f"📁 Found {len(all_folders)} folders total, checking each...")

    results = []
    for i, folder in enumerate(all_folders, 1):
        if i % 10 == 0:
            print(f"   Checked {i}/{len(all_folders)} folders...")

        # Count files in this folder
        file_query = f"'{folder['id']}' in parents and trashed=false and mimeType!='application/vnd.google-apps.folder'"
        file_result = await drive_search_files(credentials, file_query)
        files = file_result.get('files', [])
        file_count = len(files)

        if file_count >= min_files:
            # Get path
            try:
                folder_obj = service.files().get(fileId=folder['id'], fields='id,name,parents').execute()
                path = [folder_obj['name']]
                current = folder_obj

                while 'parents' in current and current['parents']:
                    parent_id = current['parents'][0]
                    try:
                        parent = service.files().get(fileId=parent_id, fields='id,name,parents').execute()
                        path.insert(0, parent['name'])
                        current = parent
                    except:
                        break

                folder_path = ' / '.join(path)
            except:
                folder_path = folder['name']

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

            results.append({
                'id': folder['id'],
                'name': folder['name'],
                'path': folder_path,
                'file_count': file_count,
                'types': types
            })

    return results


async def main():
    print("=" * 70)
    print("Find All Large Folders")
    print("=" * 70)

    from tools.google_api_client import create_api_client_auto

    try:
        client = create_api_client_auto()
        credentials = client.credentials
        print("✅ Credentials loaded\n")
    except Exception as e:
        print(f"❌ Failed to load credentials: {e}")
        return

    # Find folders with at least 10 files
    large_folders = await find_large_folders(credentials, min_files=10)

    if not large_folders:
        print("\n❌ No folders found with 10+ files")
        print("\n💡 Your documents might be:")
        print("   1. On your local computer (not uploaded to Drive)")
        print("   2. In a folder with fewer than 10 files")
        print("   3. Trashed or deleted")
        return

    # Sort by file count
    large_folders.sort(key=lambda x: x['file_count'], reverse=True)

    print("\n" + "=" * 70)
    print(f"FOUND {len(large_folders)} FOLDER(S) WITH 10+ FILES")
    print("=" * 70)

    for i, folder in enumerate(large_folders, 1):
        print(f"\n{i}. 📁 {folder['name']}")
        print(f"   Path: {folder['path']}")
        print(f"   Folder ID: {folder['id']}")
        print(f"   Files: {folder['file_count']}")

        if folder['types']:
            type_str = ', '.join(f"{k}: {v}" for k, v in folder['types'].items())
            print(f"   Types: {type_str}")

        # Highlight if this is the 117 files folder
        if folder['file_count'] == 117:
            print(f"   ⭐⭐⭐ THIS IS IT! Your 117 documents! ⭐⭐⭐")
        elif folder['file_count'] > 100:
            print(f"   🎯 Large folder - could be your invoices!")

    # Instructions
    print("\n" + "=" * 70)
    print("NEXT STEPS")
    print("=" * 70)

    # Check for 117 files folder
    target_folder = next((f for f in large_folders if f['file_count'] == 117), None)

    if target_folder:
        print(f"\n✅ Found folder with exactly 117 files!")
        print(f"   Folder: {target_folder['name']}")
        print(f"   Path: {target_folder['path']}")
        print(f"   ID: {target_folder['id']}")

        print(f"\n💡 Options:")
        print(f"   1. Move files to ADK_Workspace/Invoices_Input/")
        print(f"   2. Process directly from this folder (I can create custom script)")

        print(f"\n🤔 Which option do you prefer?")
    else:
        print(f"\n📊 Top folders by file count:")
        for folder in large_folders[:3]:
            print(f"   - {folder['name']}: {folder['file_count']} files")

        print(f"\n💡 If one of these is your invoice folder, let me know!")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
