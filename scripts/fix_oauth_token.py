"""
Fix Expired OAuth Token

Deletes all expired token files and forces fresh re-authentication.

Usage:
    py scripts/fix_oauth_token.py
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Fix encoding on Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')


def find_and_delete_token_files():
    """Find and delete all token files"""
    print("=" * 70)
    print("OAuth Token Cleanup")
    print("=" * 70)

    deleted_count = 0

    # Possible token locations
    possible_locations = [
        Path.home() / ".google_workspace_adk" / "tokens.json",
        Path.home() / ".google" / "token.json",
        Path(project_root) / "token.json",
        Path(project_root) / "auth" / "token.json",
        Path(project_root) / ".auth" / "token.json",
        Path(project_root) / "tokens.json",
    ]

    print("\n🔍 Searching for token files...")
    for path in possible_locations:
        if path.exists():
            print(f"   Found: {path}")
            try:
                path.unlink()
                print(f"   ✅ Deleted: {path}")
                deleted_count += 1
            except Exception as e:
                print(f"   ❌ Failed to delete: {e}")
        else:
            print(f"   ⏭️  Not found: {path}")

    print("\n" + "=" * 70)

    if deleted_count > 0:
        print(f"✅ Deleted {deleted_count} token file(s)")
    else:
        print("ℹ️  No token files found to delete")

    print("\n📋 Next Steps:")
    print("   1. Run: py main.py")
    print("   2. Browser will open for OAuth consent")
    print("   3. Sign in with Google account")
    print("   4. Grant all permissions")
    print("   5. New token will be created")
    print("\n   After authentication:")
    print("   6. Run: py scripts/batch_process_invoices.py")

    print("\n" + "=" * 70)


def main():
    find_and_delete_token_files()


if __name__ == "__main__":
    main()
