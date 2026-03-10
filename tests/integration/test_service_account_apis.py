#!/usr/bin/env python3
"""
Service Account API Test
Testira API-je koji rade sa Service Account-om (bez Domain-Wide Delegation)

NAPOMENA: Gmail zahtijeva Domain-Wide Delegation ili OAuth.
Ovaj test provjerava Drive, Calendar koji rade direktno sa Service Account.
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()

from auth.credential_store import get_credential_store


class ServiceAccountAPITester:
    """Testira API-je sa Service Account credentials"""

    def __init__(self):
        self.credentials = None

    def print_header(self, title: str):
        logger.info("\n" + "="*70)
        logger.info(f"  {title}")
        logger.info("="*70)

    def print_step(self, step: str):
        logger.info(f"\n▶ {step}")
        logger.info("-" * 70)

    # ========================================================================
    # STEP 1: Get Credentials
    # ========================================================================

    def setup_credentials(self) -> bool:
        """Setup Service Account credentials"""
        self.print_step("STEP 1: Loading Service Account Credentials")

        try:
            store = get_credential_store()
            self.credentials = store.get_credentials()

            if self.credentials:
                logger.info("✅ Service Account credentials loaded")
                if hasattr(self.credentials, 'service_account_email'):
                    logger.info(f"   Email: {self.credentials.service_account_email}")
                return True
            else:
                logger.error("❌ No credentials available")
                return False

        except Exception as e:
            logger.error(f"❌ Failed to load credentials: {e}")
            return False

    # ========================================================================
    # TEST: Drive API
    # ========================================================================

    def test_drive_api(self) -> bool:
        """Test Google Drive API"""
        self.print_step("STEP 2: Testing Google Drive API")

        try:
            from googleapiclient.discovery import build
            from googleapiclient.errors import HttpError

            logger.info("Building Drive service...")
            service = build('drive', 'v3', credentials=self.credentials)

            logger.info("Fetching files from Drive...")

            # List files
            results = service.files().list(
                pageSize=10,
                fields="files(id, name, mimeType, createdTime, owners)"
            ).execute()

            files = results.get('files', [])

            if not files:
                logger.warning("⚠️  No files found in Service Account's Drive")
                logger.info("This is normal - Service Account has its own isolated Drive")
                return True

            logger.info(f"✅ Found {len(files)} files in Service Account Drive!")

            logger.info("\n📁 Files:")
            logger.info("-" * 70)
            for i, file in enumerate(files, 1):
                logger.info(f"{i}. {file['name']}")
                logger.info(f"   Type: {file['mimeType']}")
                logger.info(f"   Created: {file.get('createdTime', 'Unknown')}")

            logger.info("-" * 70)

            # Try to create a test file
            logger.info("\nℹ️  Service Account can create files in its own Drive")
            logger.info("   (These won't appear in your personal Drive)")

            return True

        except HttpError as e:
            logger.error(f"❌ Drive API Error: {e}")
            if e.resp.status == 403:
                logger.info("Enable Drive API: https://console.cloud.google.com/apis/library/drive.googleapis.com")
            return False

        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return False

    # ========================================================================
    # TEST: Calendar API
    # ========================================================================

    def test_calendar_api(self) -> bool:
        """Test Google Calendar API"""
        self.print_step("STEP 3: Testing Google Calendar API")

        try:
            from googleapiclient.discovery import build
            from googleapiclient.errors import HttpError
            import pytz

            logger.info("Building Calendar service...")
            service = build('calendar', 'v3', credentials=self.credentials)

            logger.info("Fetching calendar list...")

            # List calendars
            calendars_result = service.calendarList().list().execute()
            calendars = calendars_result.get('items', [])

            if not calendars:
                logger.warning("⚠️  No calendars found for Service Account")
                logger.info("Service Account has its own isolated calendar")
                return True

            logger.info(f"✅ Found {len(calendars)} calendars!")

            # Get today's events from primary calendar
            now = datetime.now(pytz.UTC)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)

            logger.info(f"\nFetching today's events ({today_start.date()})...")

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
                logger.info("ℹ️  No events today in Service Account calendar")
            else:
                logger.info(f"✅ Found {len(events)} events today!")
                logger.info("\n📅 Today's Events:")
                logger.info("-" * 70)
                for i, event in enumerate(events, 1):
                    start = event['start'].get('dateTime', event['start'].get('date'))
                    logger.info(f"{i}. {event.get('summary', 'No Title')}")
                    logger.info(f"   Start: {start}")
                logger.info("-" * 70)

            return True

        except HttpError as e:
            logger.error(f"❌ Calendar API Error: {e}")
            if e.resp.status == 403:
                logger.info("Enable Calendar API: https://console.cloud.google.com/apis/library/calendar-json.googleapis.com")
            return False

        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return False

    # ========================================================================
    # EXPLANATION: Gmail Issue
    # ========================================================================

    def explain_gmail_issue(self):
        """Objasni Gmail problem"""
        self.print_header("📧 ABOUT GMAIL API ACCESS")

        logger.info("""
Gmail API is SPECIAL and requires one of these:

1️⃣  DOMAIN-WIDE DELEGATION (for Google Workspace)
   - Requires Google Workspace Admin access
   - Service Account can impersonate users
   - Steps: https://developers.google.com/workspace/guides/create-credentials#service-account

2️⃣  OAUTH 2.0 FLOW (for Personal Gmail)
   - Opens browser for user authorization
   - Gets user token
   - Works with personal Gmail accounts

3️⃣  USER IMPERSONATION (with Domain-Wide Delegation)
   - Set delegated_user in Service Account
   - Example: delegated_user='you@yourdomain.com'

Your current setup:
   ✅ Service Account works fine
   ❌ Gmail requires additional setup
   ✅ Drive & Calendar work with Service Account

RECOMMENDED NEXT STEP:
   Setup OAuth 2.0 for Gmail access (I can help with this!)
        """)

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
            logger.info("\n🎉 ALL SERVICE ACCOUNT APIs WORKING!")
            logger.info("Ready to setup OAuth for Gmail access")
        elif rate >= 50:
            logger.info("\n⚠️  SOME APIs WORKING")
            logger.info("Review failed tests and enable missing APIs")
        else:
            logger.info("\n❌ MOST TESTS FAILED")
            logger.info("Check API enablement and Service Account permissions")

    # ========================================================================
    # Main Flow
    # ========================================================================

    async def run_tests(self):
        """Run all Service Account tests"""
        self.print_header("SERVICE ACCOUNT API TEST")

        results = {}

        # Setup credentials
        if not self.setup_credentials():
            logger.error("Cannot proceed without credentials")
            return False

        # Test Drive
        logger.info("\nℹ️  Testing Drive API (works with Service Account)")
        input("Press ENTER to test Drive API... ")
        results['Drive API'] = self.test_drive_api()

        # Test Calendar
        logger.info("\nℹ️  Testing Calendar API (works with Service Account)")
        input("Press ENTER to test Calendar API... ")
        results['Calendar API'] = self.test_calendar_api()

        # Summary
        self.print_summary(results)

        # Explain Gmail
        self.explain_gmail_issue()

        return all(results.values())


async def main():
    tester = ServiceAccountAPITester()
    success = await tester.run_tests()

    if success:
        logger.info("\n✅ Service Account APIs working!")
        logger.info("\n📋 NEXT STEPS:")
        logger.info("   1. Drive & Calendar work with Service Account ✅")
        logger.info("   2. For Gmail: Need OAuth 2.0 setup")
        logger.info("   3. I can create OAuth flow test next!")
    else:
        logger.info("\n⚠️  Some APIs need configuration")


if __name__ == "__main__":
    asyncio.run(main())
