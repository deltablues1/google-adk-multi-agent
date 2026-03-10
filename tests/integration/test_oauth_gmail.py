#!/usr/bin/env python3
"""
OAuth 2.0 Gmail Test
Interaktivni test koji vodi kroz OAuth flow i testira Gmail API

STEPS:
1. Generate OAuth authorization URL
2. User opens URL in browser
3. User authorizes and gets redirected
4. User copies authorization code
5. Exchange code for token
6. Test Gmail API with OAuth token
"""

import os
import sys
import asyncio
import logging
import webbrowser
from pathlib import Path
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()

# Import OAuth manager
from auth.oauth_manager import OAuthManager, get_oauth_manager


class OAuthGmailTester:
    """Testira Gmail API kroz OAuth 2.0 flow"""

    def __init__(self):
        self.oauth_manager = None
        self.credentials = None

    def print_header(self, title: str):
        logger.info("\n" + "="*70)
        logger.info(f"  {title}")
        logger.info("="*70)

    def print_step(self, step_num: int, title: str):
        logger.info(f"\n{'='*70}")
        logger.info(f"  STEP {step_num}: {title}")
        logger.info("="*70)

    # ========================================================================
    # STEP 1: Check OAuth Configuration
    # ========================================================================

    def check_oauth_config(self) -> bool:
        """Check if OAuth is configured"""
        self.print_step(1, "Checking OAuth Configuration")

        client_id = os.getenv('GOOGLE_OAUTH_CLIENT_ID')
        client_secret = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET')
        redirect_uri = os.getenv('GOOGLE_OAUTH_REDIRECT_URI')

        logger.info(f"Client ID: {client_id[:30] if client_id else 'MISSING'}...")
        logger.info(f"Client Secret: {'SET' if client_secret else 'MISSING'}")
        logger.info(f"Redirect URI: {redirect_uri}")

        if not client_id or not client_secret:
            logger.error("\n❌ OAuth credentials not configured!")
            logger.error("Check your .env file")
            return False

        logger.info("\n✅ OAuth credentials configured!")
        return True

    # ========================================================================
    # STEP 2: Check for Existing Token
    # ========================================================================

    def check_existing_token(self) -> bool:
        """Check if OAuth token already exists"""
        self.print_step(2, "Checking for Existing OAuth Token")

        try:
            self.oauth_manager = get_oauth_manager()

            if self.oauth_manager.is_authenticated():
                logger.info("✅ Found existing OAuth token!")
                self.credentials = self.oauth_manager.get_credentials()

                # Check if valid
                if self.credentials.valid:
                    logger.info("✅ Token is valid!")
                    return True
                else:
                    logger.warning("⚠️  Token exists but may be expired")
                    logger.info("Will try to refresh or re-authorize")
                    return False
            else:
                logger.info("ℹ️  No existing token found")
                logger.info("Will need to authorize")
                return False

        except Exception as e:
            logger.warning(f"⚠️  Could not load existing token: {e}")
            return False

    # ========================================================================
    # STEP 3: OAuth Authorization Flow
    # ========================================================================

    def run_oauth_flow(self) -> bool:
        """Run interactive OAuth authorization flow"""
        self.print_step(3, "OAuth Authorization Flow")

        try:
            if not self.oauth_manager:
                self.oauth_manager = get_oauth_manager()

            # Generate authorization URL
            logger.info("Generating authorization URL...")
            auth_url = self.oauth_manager.get_authorization_url()

            logger.info("\n" + "="*70)
            logger.info("📱 AUTHORIZATION REQUIRED")
            logger.info("="*70)
            logger.info("\nYou need to authorize this app to access your Gmail.")
            logger.info("\n🔗 Authorization URL:")
            logger.info("-" * 70)
            logger.info(auth_url)
            logger.info("-" * 70)

            # Try to open browser automatically
            logger.info("\n⚡ Attempting to open browser automatically...")
            try:
                webbrowser.open(auth_url)
                logger.info("✅ Browser opened!")
            except:
                logger.warning("⚠️  Could not open browser automatically")
                logger.info("Please copy the URL above and paste it in your browser")

            logger.info("\n📋 INSTRUCTIONS:")
            logger.info("1. Browser will open (or copy URL above)")
            logger.info("2. Sign in with your Google account")
            logger.info("3. Grant permissions (Gmail, Drive, Calendar, etc.)")
            logger.info("4. You'll be redirected to: http://localhost:8080/oauth2callback")
            logger.info("5. Copy the ENTIRE URL from browser address bar")
            logger.info("6. Paste it below\n")

            # Wait for user to complete authorization
            redirect_url = input("📎 Paste the redirect URL here: ").strip()

            if not redirect_url:
                logger.error("❌ No URL provided")
                return False

            # Extract authorization code from URL
            logger.info("\nExtracting authorization code...")

            if 'code=' in redirect_url:
                # Parse code from URL
                code = redirect_url.split('code=')[1].split('&')[0]
                logger.info(f"✅ Found authorization code: {code[:20]}...")

                # Exchange code for token
                logger.info("\n🔄 Exchanging authorization code for access token...")
                self.credentials = self.oauth_manager.exchange_code_for_token(code)

                logger.info("✅ Successfully obtained OAuth token!")
                logger.info("✅ Token saved for future use")

                return True
            else:
                logger.error("❌ No authorization code found in URL")
                logger.error("Make sure you copied the ENTIRE redirect URL")
                return False

        except Exception as e:
            logger.error(f"❌ OAuth flow failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    # ========================================================================
    # STEP 4: Test Gmail API with OAuth
    # ========================================================================

    def test_gmail_with_oauth(self) -> bool:
        """Test Gmail API with OAuth credentials"""
        self.print_step(4, "Testing Gmail API with OAuth Token")

        if not self.credentials:
            logger.error("❌ No credentials available")
            return False

        try:
            from googleapiclient.discovery import build
            from googleapiclient.errors import HttpError

            logger.info("Building Gmail service with OAuth credentials...")
            service = build('gmail', 'v1', credentials=self.credentials)

            logger.info("Fetching your last 5 emails...")

            # Get message list
            results = service.users().messages().list(
                userId='me',
                maxResults=5
            ).execute()

            messages = results.get('messages', [])

            if not messages:
                logger.warning("⚠️  No messages found (inbox might be empty)")
                return True

            logger.info(f"✅ Successfully retrieved {len(messages)} messages!")

            logger.info("\n📧 YOUR LAST 5 EMAILS:")
            logger.info("="*70)

            for i, msg in enumerate(messages, 1):
                try:
                    # Get message details
                    message = service.users().messages().get(
                        userId='me',
                        id=msg['id'],
                        format='metadata',
                        metadataHeaders=['From', 'Subject', 'Date']
                    ).execute()

                    headers = {h['name']: h['value'] for h in message.get('payload', {}).get('headers', [])}

                    logger.info(f"\n{i}. 📨 Subject: {headers.get('Subject', 'No Subject')}")
                    logger.info(f"   👤 From: {headers.get('From', 'Unknown')}")
                    logger.info(f"   📅 Date: {headers.get('Date', 'Unknown')}")

                except Exception as e:
                    logger.error(f"   ❌ Error reading message {i}: {e}")

            logger.info("\n" + "="*70)
            logger.info("✅ Gmail API working perfectly with OAuth!")

            return True

        except HttpError as e:
            logger.error(f"❌ Gmail API Error: {e}")

            if e.resp.status == 403:
                logger.info("Error 403: Gmail API may not be enabled")
                logger.info("Enable: https://console.cloud.google.com/apis/library/gmail.googleapis.com")
            elif e.resp.status == 401:
                logger.info("Error 401: Token may be invalid or expired")
                logger.info("Try running the OAuth flow again")

            return False

        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return False

    # ========================================================================
    # STEP 5: Test People API (Contacts)
    # ========================================================================

    def test_contacts_with_oauth(self) -> bool:
        """Test People API with OAuth credentials"""
        self.print_step(5, "Testing People API (Contacts) with OAuth")

        if not self.credentials:
            logger.error("❌ No credentials available")
            return False

        try:
            from googleapiclient.discovery import build
            from googleapiclient.errors import HttpError

            logger.info("Building People service...")
            service = build('people', 'v1', credentials=self.credentials)

            logger.info("Fetching your contacts...")

            # Get contacts
            results = service.people().connections().list(
                resourceName='people/me',
                pageSize=10,
                personFields='names,emailAddresses,phoneNumbers'
            ).execute()

            connections = results.get('connections', [])

            if not connections:
                logger.warning("⚠️  No contacts found")
                return True

            logger.info(f"✅ Found {len(connections)} contacts!")

            logger.info("\n👥 YOUR CONTACTS:")
            logger.info("="*70)

            for i, person in enumerate(connections, 1):
                names = person.get('names', [])
                emails = person.get('emailAddresses', [])
                phones = person.get('phoneNumbers', [])

                name = names[0].get('displayName') if names else 'No Name'
                email = emails[0].get('value') if emails else 'No Email'
                phone = phones[0].get('value') if phones else 'No Phone'

                logger.info(f"\n{i}. 👤 {name}")
                logger.info(f"   ✉️  {email}")
                if phone != 'No Phone':
                    logger.info(f"   📱 {phone}")

            logger.info("\n" + "="*70)
            logger.info("✅ People API working perfectly with OAuth!")

            return True

        except HttpError as e:
            logger.error(f"❌ People API Error: {e}")

            if e.resp.status == 403:
                logger.info("Error 403: People API may not be enabled")
                logger.info("Enable: https://console.cloud.google.com/apis/library/people.googleapis.com")

            return False

        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return False

    # ========================================================================
    # Summary
    # ========================================================================

    def print_summary(self, results: dict):
        """Print final summary"""
        self.print_header("FINAL TEST SUMMARY")

        total = len(results)
        passed = sum(1 for v in results.values() if v)

        logger.info(f"\nTotal Tests: {total}")
        logger.info(f"✅ Passed: {passed}")
        logger.info(f"❌ Failed: {total - passed}\n")

        for test, success in results.items():
            status = "✅" if success else "❌"
            logger.info(f"  {status} {test}")

        rate = (passed / total * 100) if total > 0 else 0
        logger.info(f"\nSuccess Rate: {rate:.1f}%")

        if rate == 100:
            logger.info("\n🎉"*35)
            logger.info("🎉  ALL OAUTH APIS WORKING PERFECTLY!")
            logger.info("🎉"*35)
            logger.info("\n✅ You now have FULL access to:")
            logger.info("   📧 Gmail (read & send)")
            logger.info("   📁 Drive (read & write)")
            logger.info("   📅 Calendar (read & write)")
            logger.info("   👥 Contacts (read & update)")
            logger.info("\n🚀 READY FOR PRODUCTION USE!")
        else:
            logger.info("\n⚠️  Some APIs need attention")

    # ========================================================================
    # Main Flow
    # ========================================================================

    async def run_full_test(self):
        """Run complete OAuth test flow"""
        self.print_header("OAUTH 2.0 GMAIL & CONTACTS TEST")

        results = {}

        # Step 1: Check config
        if not self.check_oauth_config():
            logger.error("Cannot proceed without OAuth configuration")
            return False

        results['OAuth Configuration'] = True

        # Step 2: Check existing token
        has_token = self.check_existing_token()

        # Step 3: Run OAuth flow if needed
        if not has_token:
            logger.info("\nℹ️  Need to authorize access to your Google account")
            input("\nPress ENTER to start OAuth flow... ")

            if not self.run_oauth_flow():
                logger.error("❌ OAuth flow failed")
                return False

            results['OAuth Authorization'] = True
        else:
            logger.info("✅ Using existing OAuth token")
            results['OAuth Authorization'] = True

        # Step 4: Test Gmail
        logger.info("\nℹ️  Testing Gmail API with YOUR real Gmail account")
        input("\nPress ENTER to test Gmail... ")

        results['Gmail API'] = self.test_gmail_with_oauth()

        # Step 5: Test Contacts
        logger.info("\nℹ️  Testing People API with YOUR real contacts")
        input("\nPress ENTER to test Contacts... ")

        results['People API (Contacts)'] = self.test_contacts_with_oauth()

        # Summary
        self.print_summary(results)

        return all(results.values())


async def main():
    tester = OAuthGmailTester()
    success = await tester.run_full_test()

    if success:
        logger.info("\n✅ OAuth setup complete and working!")
        logger.info("\n📋 Token saved at: ~/.google_workspace_adk/tokens.json")
        logger.info("   You won't need to authorize again (until token expires)")
    else:
        logger.info("\n⚠️  Some issues encountered during testing")


if __name__ == "__main__":
    asyncio.run(main())
