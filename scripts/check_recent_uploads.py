"""
Check Recent Uploads

Shows recently uploaded files to verify they're on Drive.

Usage:
    py scripts/check_recent_uploads.py
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
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


async def get_recent_uploads(credentials, hours=2):
    """Get all files uploaded in last N hours"""
    from tools.api_implementations.drive_api import drive_search_files
    from googleapiclient.discovery import build

    # Calculate time threshold
    threshold = datetime.utcnow() - timedelta(hours=hours)
    threshold_str = threshold.strftime('%Y-%m-%dT%H:%M:%S')

    print(f"🔍 Searching for files uploaded after: {threshold_str}\n")

    # Search for recent files
    query = f"createdTime > '{threshold_str}' and trashed=false and mimeType!='application/vnd.google-apps.folder'"

    result = await drive_search_files(credentials, query)
    files = result.get('files', [])

    if not files:
        print("❌ No recent uploads found")
        return []

    service = build('drive', 'v3', credentials=credentials)

    # Get parent folder info for each file
    file_details = []
    for file in files:
        try:
            file_obj = service.files().get(
                fileId=file['id'],
                fields='id,name,parents,createdTime,mimeType,size'
            ).execute()

            # Get parent folder name
            parent_name = "Root"
            if 'parents' in file_obj and file_obj['parents']:
                try:
                    parent = service.files().get(
                        fileId=file_obj['parents'][0],
                        fields='name'
                    ).execute()
                    parent_name = parent['name']
                except:
                    pass

            file_details.append({
                'name': file_obj['name'],
                'id': file_obj['id'],
                'parent': parent_name,
                'parent_id': file_obj.get('parents', [None])[0],
                'created': file_obj['createdTime'],
                'mime': file_obj['mimeType'],
                'size': file_obj.get('size', 0)
            })
        except Exception as e:
            print(f"   Warning: Could not get details for {file['name']}: {e}")

    return file_details


async def main():
    print("=" * 70)
    print("Check Recent Uploads")
    print("=" * 70)

    from tools.google_api_client import create_api_client_auto

    try:
        client = create_api_client_auto()
        credentials = client.credentials
        print("✅ Credentials loaded\n")
    except Exception as e:
        print(f"❌ Failed to load credentials: {e}")
        return

    # Get recent uploads
    recent_files = await get_recent_uploads(credentials, hours=2)

    if not recent_files:
        print("\n⚠️  No files uploaded in last 2 hours")
        print("\n💡 Possible reasons:")
        print("   1. Files were uploaded to different Google account")
        print("   2. Upload didn't complete")
        print("   3. Drive API cache delay (wait 2-3 minutes and try again)")
        return

    # Group by parent folder
    by_folder = {}
    for file in recent_files:
        parent = file['parent']
        if parent not in by_folder:
            by_folder[parent] = []
        by_folder[parent].append(file)

    print(f"✅ Found {len(recent_files)} recently uploaded file(s)")
    print("\n" + "=" * 70)
    print("FILES BY FOLDER")
    print("=" * 70)

    for folder_name, files in sorted(by_folder.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"\n📁 {folder_name} - {len(files)} file(s)")

        # Show folder ID
        if files[0]['parent_id']:
            print(f"   Folder ID: {files[0]['parent_id']}")

        # Count file types
        types = {}
        for file in files:
            mime = file['mime']
            if 'image' in mime:
                file_type = 'image'
            elif 'pdf' in mime:
                file_type = 'pdf'
            else:
                file_type = 'other'
            types[file_type] = types.get(file_type, 0) + 1

        if types:
            type_str = ', '.join(f"{k}: {v}" for k, v in types.items())
            print(f"   Types: {type_str}")

        # Show first 5 files
        print(f"   First files:")
        for file in files[:5]:
            created = file['created'].split('T')[1].split('.')[0]  # Just time
            print(f"   - {file['name']} (uploaded at {created})")

        if len(files) > 5:
            print(f"   ... and {len(files) - 5} more files")

        # Check if this is 117 files
        if len(files) == 117:
            print(f"\n   ⭐⭐⭐ THIS IS YOUR 117 FILES! ⭐⭐⭐")
        elif len(files) >= 30:
            print(f"\n   🎯 This could be your invoice batch!")

    # Summary
    print("\n" + "=" * 70)
    print("NEXT STEPS")
    print("=" * 70)

    # Find the largest batch
    largest_folder = max(by_folder.items(), key=lambda x: len(x[1]))
    folder_name, files = largest_folder

    total_files = sum(len(f) for f in by_folder.values())

    if total_files >= 117:
        print(f"\n✅ Found your {total_files} uploaded files!")

        if folder_name == "Invoices_Input":
            print(f"   ✅ They're already in the correct folder!")
            print(f"\n💡 Wait 2-3 minutes for Drive cache to update, then run:")
            print(f"   py scripts/batch_process_invoices.py")
        else:
            print(f"   📁 Currently in: {folder_name}")
            print(f"   🎯 Folder ID: {files[0]['parent_id']}")

            print(f"\n💡 Options:")
            print(f"   1. Move files to ADK_Workspace/Invoices_Input/")
            print(f"   2. Process directly from this folder")
            print(f"      (I can modify batch script to use this folder ID)")

            print(f"\n🤔 Which option do you prefer?")
    else:
        print(f"\n📊 Found {total_files} recent uploads")
        print(f"   You mentioned 117 files - where are the rest?")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
