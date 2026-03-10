#!/usr/bin/env python3
"""
Incremental Real API Test
Pažljivo testira prave Google Workspace API pozive korak po korak

FAZA:
1. Testira credentials i pristup
2. Testira jedan read poziv (Gmail list)
3. Prikazuje rezultat
4. Nastavlja samo ako je uspješno
"""

import os
import sys
import asyncio
import logging
from datetime import datetime
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

# Import auth
from auth.credential_store import get_credential_store
from auth.service_account_manager import get_service_account_manager


class IncrementalAPITester:
    """Inkrementalno testira prave API pozive"""

    def __init__(self):
        self.credential_store = None
        self.credentials = None
        self.test_results = []

    def print_header(self, title: str):
        """Ispisuje header"""
        logger.info("\n" + "="*70)
        logger.info(f"  {title}")
        logger.info("="*70)

    def print_step(self, step_num: int, description: str):
        """Ispisuje korak"""
        logger.info(f"\n▶ STEP {step_num}: {description}")
        logger.info("-" * 70)

    def print_success(self, message: str):
        """Ispisuje success"""
        logger.info(f"✅ {message}")

    def print_error(self, message: str):
        """Ispisuje error"""
        logger.error(f"❌ {message}")

    def print_warning(self, message: str):
        """Ispisuje warning"""
        logger.warning(f"⚠️  {message}")

    def print_info(self, message: str):
        """Ispisuje info"""
        logger.info(f"ℹ️  {message}")

    # ========================================================================
    # STEP 1: Test Credentials Access
    # ========================================================================

    def test_credentials_access(self) -> bool:
        """Test: Pristup credentials"""
        self.print_step(1, "Testing Credentials Access")

        try:
            # Get credential store
            self.credential_store = get_credential_store()
            logger.info("Credential store initialized")

            # Try to get credentials
            self.credentials = self.credential_store.get_credentials()

            if self.credentials:
                auth_type = self.credential_store.get_auth_type()
                self.print_success(f"Credentials found! Type: {auth_type}")

                # Display credential info (safely)
                if auth_type == 'service_account':
                    if hasattr(self.credentials, 'service_account_email'):
                        logger.info(f"   Service Account: {self.credentials.service_account_email}")
                    logger.info(f"   Scopes: {len(self.credentials.scopes) if hasattr(self.credentials, 'scopes') else 'N/A'} scopes")
                elif auth_type == 'oauth':
                    logger.info(f"   OAuth Token: {'Valid' if self.credentials.valid else 'Expired/Invalid'}")

                return True
            else:
                self.print_error("No credentials available!")
                self.print_info("You may need to run OAuth flow first")
                return False

        except Exception as e:
            self.print_error(f"Failed to access credentials: {e}")
            import traceback
            traceback.print_exc()
            return False

    # ========================================================================
    # STEP 2: Test Direct Gmail API Access
    # ========================================================================

    def test_gmail_api_direct(self) -> bool:
        """Test: Direktan pristup Gmail API-ju"""
        self.print_step(2, "Testing Direct Gmail API Access")

        if not self.credentials:
            self.print_error("No credentials available from Step 1")
            return False

        try:
            from googleapiclient.discovery import build
            from googleapiclient.errors import HttpError

            logger.info("Building Gmail service...")
            service = build('gmail', 'v1', credentials=self.credentials)

            logger.info("Requesting message list (maxResults=5)...")

            # Try to list messages
            results = service.users().messages().list(
                userId='me',
                maxResults=5
            ).execute()

            messages = results.get('messages', [])

            if not messages:
                self.print_warning("No messages found (inbox might be empty)")
                return True  # Still successful API call

            self.print_success(f"Successfully retrieved {len(messages)} messages!")

            # Get details for each message
            logger.info("\n📧 Last 5 Emails:")
            logger.info("-" * 70)

            for i, msg in enumerate(messages, 1):
                try:
                    message = service.users().messages().get(
                        userId='me',
                        id=msg['id'],
                        format='metadata',
                        metadataHeaders=['From', 'Subject', 'Date']
                    ).execute()

                    headers = {h['name']: h['value'] for h in message.get('payload', {}).get('headers', [])}

                    logger.info(f"\n{i}. Subject: {headers.get('Subject', 'No Subject')}")
                    logger.info(f"   From: {headers.get('From', 'Unknown')}")
                    logger.info(f"   Date: {headers.get('Date', 'Unknown')}")

                except Exception as e:
                    logger.error(f"   Error getting message {i}: {e}")

            logger.info("-" * 70)
            return True

        except HttpError as e:
            self.print_error(f"Gmail API HTTP Error: {e}")

            if e.resp.status == 403:
                self.print_info("Error 403: Gmail API may not be enabled")
                self.print_info("Enable it: https://console.cloud.google.com/apis/library/gmail.googleapis.com")
            elif e.resp.status == 401:
                self.print_info("Error 401: Authentication issue")
                self.print_info("Check credentials or run OAuth flow")

            return False

        except Exception as e:
            self.print_error(f"Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return False

    # ========================================================================
    # STEP 3: Test Other Read APIs
    # ========================================================================

    def test_drive_api_direct(self) -> bool:
        """Test: Direktan pristup Drive API-ju"""
        self.print_step(3, "Testing Direct Google Drive API Access")

        if not self.credentials:
            self.print_error("No credentials available")
            return False

        try:
            from googleapiclient.discovery import build
            from googleapiclient.errors import HttpError

            logger.info("Building Drive service...")
            service = build('drive', 'v3', credentials=self.credentials)

            logger.info("Requesting file list (maxResults=10)...")

            results = service.files().list(
                pageSize=10,
                fields="files(id, name, mimeType, modifiedTime)"
            ).execute()

            files = results.get('files', [])

            if not files:
                self.print_warning("No files found in Drive")
                return True

            self.print_success(f"Successfully retrieved {len(files)} files!")

            logger.info("\n📁 Files in Drive:")
            logger.info("-" * 70)

            for i, file in enumerate(files, 1):
                logger.info(f"{i}. {file['name']}")
                logger.info(f"   Type: {file['mimeType']}")
                logger.info(f"   Modified: {file.get('modifiedTime', 'Unknown')}\n")

            logger.info("-" * 70)
            return True

        except HttpError as e:
            self.print_error(f"Drive API HTTP Error: {e}")

            if e.resp.status == 403:
                self.print_info("Error 403: Drive API may not be enabled")
                self.print_info("Enable it: https://console.cloud.google.com/apis/library/drive.googleapis.com")

            return False

        except Exception as e:
            self.print_error(f"Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def test_calendar_api_direct(self) -> bool:
        """Test: Direktan pristup Calendar API-ju"""
        self.print_step(4, "Testing Direct Google Calendar API Access")

        if not self.credentials:
            self.print_error("No credentials available")
            return False

        try:
            from googleapiclient.discovery import build
            from googleapiclient.errors import HttpError
            from datetime import datetime, timedelta
            import pytz

            logger.info("Building Calendar service...")
            service = build('calendar', 'v3', credentials=self.credentials)

            # Get today's events
            now = datetime.now(pytz.UTC)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)

            logger.info(f"Requesting events for today ({today_start.date()})...")

            events_result = service.events().list(
                calendarId='primary',
                timeMin=today_start.isoformat(),
                timeMax=today_end.isoformat(),
                maxResults=10,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])

            if not events:
                self.print_warning("No events today")
                return True

            self.print_success(f"Successfully retrieved {len(events)} events!")

            logger.info("\n📅 Today's Calendar Events:")
            logger.info("-" * 70)

            for i, event in enumerate(events, 1):
                start = event['start'].get('dateTime', event['start'].get('date'))
                logger.info(f"{i}. {event['summary']}")
                logger.info(f"   Start: {start}\n")

            logger.info("-" * 70)
            return True

        except HttpError as e:
            self.print_error(f"Calendar API HTTP Error: {e}")

            if e.resp.status == 403:
                self.print_info("Error 403: Calendar API may not be enabled")
                self.print_info("Enable it: https://console.cloud.google.com/apis/library/calendar-json.googleapis.com")

            return False

        except Exception as e:
            self.print_error(f"Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return False

    # ========================================================================
    # STEP 4: Test People API (Contacts)
    # ========================================================================

    def test_contacts_api_direct(self) -> bool:
        """Test: Direktan pristup People API-ju (Contacts)"""
        self.print_step(5, "Testing Direct Google People API Access (Contacts)")

        if not self.credentials:
            self.print_error("No credentials available")
            return False

        try:
            from googleapiclient.discovery import build
            from googleapiclient.errors import HttpError

            logger.info("Building People service...")
            service = build('people', 'v1', credentials=self.credentials)

            logger.info("Requesting contacts list (pageSize=10)...")

            results = service.people().connections().list(
                resourceName='people/me',
                pageSize=10,
                personFields='names,emailAddresses,phoneNumbers'
            ).execute()

            connections = results.get('connections', [])

            if not connections:
                self.print_warning("No contacts found")
                return True

            self.print_success(f"Successfully retrieved {len(connections)} contacts!")

            logger.info("\n👥 Contacts:")
            logger.info("-" * 70)

            for i, person in enumerate(connections, 1):
                names = person.get('names', [])
                emails = person.get('emailAddresses', [])

                name = names[0].get('displayName', 'No Name') if names else 'No Name'
                email = emails[0].get('value', 'No Email') if emails else 'No Email'

                logger.info(f"{i}. {name}")
                logger.info(f"   Email: {email}\n")

            logger.info("-" * 70)
            return True

        except HttpError as e:
            self.print_error(f"People API HTTP Error: {e}")

            if e.resp.status == 403:
                self.print_info("Error 403: People API may not be enabled")
                self.print_info("Enable it: https://console.cloud.google.com/apis/library/people.googleapis.com")

            return False

        except Exception as e:
            self.print_error(f"Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return False

    # ========================================================================
    # Summary
    # ========================================================================

    def print_final_summary(self, results: dict):
        """Ispisuje finalni sažetak"""
        self.print_header("FINAL TEST SUMMARY")

        total = len(results)
        passed = sum(1 for v in results.values() if v)

        logger.info(f"\nTotal Tests: {total}")
        logger.info(f"✅ Passed: {passed}")
        logger.info(f"❌ Failed: {total - passed}")
        logger.info("")

        for test_name, success in results.items():
            status = "✅ PASSED" if success else "❌ FAILED"
            logger.info(f"  {status}: {test_name}")

        success_rate = (passed / total * 100) if total > 0 else 0
        logger.info(f"\nSuccess Rate: {success_rate:.1f}%")

        if success_rate == 100:
            logger.info("\n" + "🎉"*35)
            logger.info("🎉  ALL TESTS PASSED! SYSTEM FULLY OPERATIONAL!")
            logger.info("🎉"*35)
            logger.info("\n📋 Next Steps:")
            logger.info("  1. All Google Workspace APIs are working correctly")
            logger.info("  2. Ready for WRITE operations (with your approval)")
            logger.info("  3. Can proceed to test:")
            logger.info("     - Sending emails")
            logger.info("     - Creating documents")
            logger.info("     - Updating contacts")
        elif success_rate >= 50:
            logger.info("\n⚠️  PARTIAL SUCCESS - Some APIs working, some need configuration")
            logger.info("Review failed tests and enable missing APIs")
        else:
            logger.info("\n❌ MOST TESTS FAILED - Review configuration and API enablement")

    # ========================================================================
    # Main Execution Flow
    # ========================================================================

    async def run_incremental_tests(self):
        """Pokreni sve testove inkrementalno"""
        self.print_header("GOOGLE WORKSPACE ADK - INCREMENTAL API TEST")

        results = {}

        # Step 1: Credentials
        logger.info("\n🔐 PHASE 1: AUTHENTICATION")
        if not self.test_credentials_access():
            self.print_error("Cannot proceed without credentials!")
            return False

        results['Credentials Access'] = True

        # Step 2: Gmail (prva read operacija)
        logger.info("\n📧 PHASE 2: GMAIL API (First Read Test)")
        self.print_info("Testing with your real Gmail account...")
        input("\nPress ENTER to continue with Gmail test... ")

        gmail_success = self.test_gmail_api_direct()
        results['Gmail API'] = gmail_success

        if not gmail_success:
            self.print_warning("Gmail test failed - stopping here")
            self.print_final_summary(results)
            return False

        # Continue to other read operations
        logger.info("\n📁 PHASE 3: OTHER READ OPERATIONS")
        self.print_info("Testing Drive, Calendar, and Contacts...")
        input("\nPress ENTER to continue with other read tests... ")

        results['Drive API'] = self.test_drive_api_direct()
        results['Calendar API'] = self.test_calendar_api_direct()
        results['Contacts API'] = self.test_contacts_api_direct()

        # Final summary
        self.print_final_summary(results)

        return all(results.values())


async def main():
    """Main entry point"""
    tester = IncrementalAPITester()
    success = await tester.run_incremental_tests()

    if success:
        logger.info("\n✅ All read operations successful!")
        logger.info("Ready for write operations (Phase 4)")
    else:
        logger.info("\n⚠️  Some tests failed. Review and fix before proceeding.")


if __name__ == "__main__":
    asyncio.run(main())
