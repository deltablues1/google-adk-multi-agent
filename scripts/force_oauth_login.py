"""
Force OAuth Login

Forces OAuth authentication flow and opens browser.

Usage:
    py scripts/force_oauth_login.py
"""

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


def main():
    print("=" * 70)
    print("Force OAuth Authentication")
    print("=" * 70)

    import json
    from pathlib import Path
    from google_auth_oauthlib.flow import InstalledAppFlow

    # Check for oauth_client_credentials.json
    creds_file = os.path.join(project_root, 'oauth_client_credentials.json')

    if not os.path.exists(creds_file):
        print(f"\n❌ Error: oauth_client_credentials.json not found!")
        print(f"   Expected location: {creds_file}")
        print("\n💡 Please ensure OAuth credentials file exists")
        return

    print(f"\n✅ Found credentials file: oauth_client_credentials.json")

    # OAuth scopes - must match auth/oauth_manager.py OAuthManager.SCOPES
    from auth.oauth_manager import OAuthManager
    SCOPES = OAuthManager.SCOPES

    print("\n🔑 Starting OAuth authentication flow...")
    print("   Browser will open automatically in a few seconds...")
    print("   If browser doesn't open, you'll see a URL to open manually\n")

    try:
        # Create flow from client secrets file
        flow = InstalledAppFlow.from_client_secrets_file(
            creds_file,
            scopes=SCOPES
        )

        # Run local server to handle OAuth callback
        # This will open browser automatically
        print("🌐 Opening browser for authentication...")
        credentials = flow.run_local_server(
            port=8080,
            open_browser=True,
            authorization_prompt_message='Please visit this URL to authorize: {url}',
            success_message='Authentication successful! You can close this window.'
        )

        if credentials and credentials.valid:
            print("\n✅ Authentication successful!")

            # Save token to expected location
            token_dir = Path.home() / '.google_workspace_adk'
            token_dir.mkdir(exist_ok=True)
            token_path = token_dir / 'tokens.json'

            # Save credentials
            token_data = {
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes
            }

            with open(token_path, 'w') as f:
                json.dump(token_data, f, indent=2)

            print(f"   Token saved to: {token_path}")

            print("\n📋 Granted permissions:")
            if credentials.scopes:
                for scope in credentials.scopes[:8]:  # Show first 8
                    scope_name = scope.split('/')[-1]
                    print(f"   ✓ {scope_name}")
                if len(credentials.scopes) > 8:
                    print(f"   ... and {len(credentials.scopes) - 8} more")

            print("\n✅ You can now run batch processing:")
            print("   py scripts/batch_process_invoices.py")

            print("\n✅ Or test with main.py:")
            print("   py main.py")
        else:
            print("\n❌ Authentication failed!")
            print("   Credentials are not valid")

    except Exception as e:
        print(f"\n❌ Authentication error: {e}")
        import traceback
        traceback.print_exc()

        print("\n💡 Troubleshooting:")
        print("   1. Check oauth_client_credentials.json is valid JSON")
        print("   2. Verify OAuth Client ID and Secret are correct")
        print("   3. Check redirect URI includes: http://localhost:8080")
        print("   4. Ensure OAuth consent screen is configured in Google Cloud")
        print("   5. Make sure port 8080 is not in use")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
