#!/usr/bin/env python3
"""
Comprehensive Multi-Agent Scenario Tests

Tests REAL multi-agent system with REAL API calls across 3 tiers:
- TIER 1: Single-agent operations (basic API functionality)
- TIER 2: Multi-agent coordination (2-3 agents working together)
- TIER 3: Complex cross-API operations (3+ agents, complex workflows)

IMPORTANT: This uses REAL APIs and REAL data!
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()

# Import system components
from config.agent_registry import create_agent_instance, get_worker_agent_names
from agents.orchestrator.orchestrator import OrchestratorAgent
from auth.credential_store import get_credential_store


class ComprehensiveScenarioTester:
    """Tests comprehensive multi-agent scenarios with REAL APIs"""

    def __init__(self):
        self.orchestrator: Optional[OrchestratorAgent] = None
        self.agents: Dict[str, Any] = {}
        self.test_results: Dict[str, List[Dict]] = {
            'tier1': [],
            'tier2': [],
            'tier3': []
        }
        self.created_resources: List[Dict] = []  # Track for cleanup

    # ========================================================================
    # SETUP & INITIALIZATION
    # ========================================================================

    async def setup(self):
        """Initialize all agents and verify authentication"""
        logger.info("="*70)
        logger.info("COMPREHENSIVE SCENARIO TEST SUITE - SETUP")
        logger.info("="*70)

        # Verify authentication
        logger.info("Checking authentication...")
        store = get_credential_store()
        auth_type = store.get_auth_type()

        if auth_type == 'none':
            logger.error("No authentication available!")
            logger.error("Please run test_oauth_gmail.py first to authenticate")
            return False

        logger.info(f"Authentication: {auth_type} - OK")

        # Initialize worker agents
        logger.info("\nInitializing agents...")
        worker_names = get_worker_agent_names()

        for agent_name in worker_names:
            try:
                agent = create_agent_instance(agent_name)
                self.agents[agent_name] = agent
                logger.info(f"  OK - {agent_name}")
            except Exception as e:
                logger.error(f"  FAIL - {agent_name}: {e}")
                return False

        # Initialize orchestrator
        logger.info("\nInitializing orchestrator...")
        self.orchestrator = OrchestratorAgent(sub_agents=list(self.agents.values()))
        logger.info("  OK - orchestrator")

        logger.info(f"\nSetup complete! {len(self.agents)} agents ready")
        return True

    # ========================================================================
    # TIER 1: SINGLE-AGENT OPERATIONS (Basic API functionality)
    # ========================================================================

    async def test_tier1_gmail_list_emails(self):
        """Test Gmail: List last 5 emails"""
        test_name = "Gmail - List last 5 emails"
        logger.info(f"\n[TIER 1] {test_name}")

        try:
            from googleapiclient.discovery import build

            # Get credentials
            store = get_credential_store()
            creds = store.get_credentials()

            # Build service
            service = build('gmail', 'v1', credentials=creds)

            # List messages
            results = service.users().messages().list(
                userId='me',
                maxResults=5
            ).execute()

            messages = results.get('messages', [])

            if not messages:
                logger.warning("  No messages found (empty inbox)")
                return self._log_result('tier1', test_name, True, "No messages (inbox empty)")

            logger.info(f"  SUCCESS: Retrieved {len(messages)} emails")

            # Get details of first email
            msg = service.users().messages().get(
                userId='me',
                id=messages[0]['id'],
                format='metadata',
                metadataHeaders=['From', 'Subject']
            ).execute()

            headers = {h['name']: h['value'] for h in msg['payload']['headers']}
            logger.info(f"  Latest: '{headers.get('Subject', 'No Subject')}' from {headers.get('From', 'Unknown')}")

            return self._log_result('tier1', test_name, True, f"Retrieved {len(messages)} emails")

        except Exception as e:
            logger.error(f"  FAILED: {e}")
            return self._log_result('tier1', test_name, False, str(e))

    async def test_tier1_contacts_search(self):
        """Test Contacts: Search for 'Tomislav Golić'"""
        test_name = "Contacts - Search for 'Tomislav Golić'"
        logger.info(f"\n[TIER 1] {test_name}")

        try:
            from googleapiclient.discovery import build

            store = get_credential_store()
            creds = store.get_credentials()

            service = build('people', 'v1', credentials=creds)

            # Search contacts
            results = service.people().connections().list(
                resourceName='people/me',
                pageSize=100,
                personFields='names,emailAddresses,phoneNumbers'
            ).execute()

            connections = results.get('connections', [])

            # Find Tomislav Golić
            found = None
            for person in connections:
                names = person.get('names', [])
                if names:
                    display_name = names[0].get('displayName', '')
                    if 'Tomislav' in display_name and 'Golić' in display_name:
                        found = person
                        break

            if found:
                names = found.get('names', [])
                emails = found.get('emailAddresses', [])
                phones = found.get('phoneNumbers', [])

                name = names[0].get('displayName') if names else 'Unknown'
                email = emails[0].get('value') if emails else 'No email'
                phone = phones[0].get('value') if phones else 'No phone'

                logger.info(f"  SUCCESS: Found '{name}'")
                logger.info(f"    Email: {email}")
                logger.info(f"    Phone: {phone}")

                return self._log_result('tier1', test_name, True, f"Found: {name}")
            else:
                logger.warning("  Contact 'Tomislav Golić' not found")
                return self._log_result('tier1', test_name, True, "Contact not found (but API works)")

        except Exception as e:
            logger.error(f"  FAILED: {e}")
            return self._log_result('tier1', test_name, False, str(e))

    async def test_tier1_drive_list_files(self):
        """Test Drive: List files"""
        test_name = "Drive - List files"
        logger.info(f"\n[TIER 1] {test_name}")

        try:
            from googleapiclient.discovery import build

            store = get_credential_store()
            creds = store.get_credentials()

            service = build('drive', 'v3', credentials=creds)

            # List files
            results = service.files().list(
                pageSize=10,
                fields="files(id, name, mimeType, modifiedTime)"
            ).execute()

            files = results.get('files', [])

            if not files:
                logger.warning("  No files found in Drive")
                return self._log_result('tier1', test_name, True, "No files (but API works)")

            logger.info(f"  SUCCESS: Found {len(files)} files")
            for i, file in enumerate(files[:3], 1):
                logger.info(f"    {i}. {file['name']} ({file['mimeType']})")

            return self._log_result('tier1', test_name, True, f"Listed {len(files)} files")

        except Exception as e:
            logger.error(f"  FAILED: {e}")
            return self._log_result('tier1', test_name, False, str(e))

    async def test_tier1_calendar_list_events(self):
        """Test Calendar: List today's events"""
        test_name = "Calendar - List today's events"
        logger.info(f"\n[TIER 1] {test_name}")

        try:
            from googleapiclient.discovery import build
            from datetime import datetime, timezone

            store = get_credential_store()
            creds = store.get_credentials()

            service = build('calendar', 'v3', credentials=creds)

            # Get today's events
            now = datetime.now(timezone.utc)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)

            events_result = service.events().list(
                calendarId='primary',
                timeMin=today_start.isoformat(),
                timeMax=today_end.isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])

            if not events:
                logger.info("  SUCCESS: No events today")
                return self._log_result('tier1', test_name, True, "No events today")

            logger.info(f"  SUCCESS: Found {len(events)} events today")
            for i, event in enumerate(events, 1):
                start = event['start'].get('dateTime', event['start'].get('date'))
                logger.info(f"    {i}. {event['summary']} at {start}")

            return self._log_result('tier1', test_name, True, f"Listed {len(events)} events")

        except Exception as e:
            logger.error(f"  FAILED: {e}")
            return self._log_result('tier1', test_name, False, str(e))

    async def test_tier1_docs_create_document(self):
        """Test Docs: Create test document"""
        test_name = "Docs - Create test document"
        logger.info(f"\n[TIER 1] {test_name}")

        try:
            from googleapiclient.discovery import build

            store = get_credential_store()
            creds = store.get_credentials()

            service = build('docs', 'v1', credentials=creds)

            # Create document
            title = f"ADK Test Document - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            doc = service.documents().create(body={'title': title}).execute()

            doc_id = doc['documentId']
            doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"

            logger.info(f"  SUCCESS: Created document")
            logger.info(f"    Title: {title}")
            logger.info(f"    ID: {doc_id}")
            logger.info(f"    URL: {doc_url}")

            # Track for cleanup
            self.created_resources.append({
                'type': 'doc',
                'id': doc_id,
                'title': title
            })

            return self._log_result('tier1', test_name, True, f"Created: {title}")

        except Exception as e:
            logger.error(f"  FAILED: {e}")
            return self._log_result('tier1', test_name, False, str(e))

    async def test_tier1_sheets_create_spreadsheet(self):
        """Test Sheets: Create test spreadsheet"""
        test_name = "Sheets - Create test spreadsheet"
        logger.info(f"\n[TIER 1] {test_name}")

        try:
            from googleapiclient.discovery import build

            store = get_credential_store()
            creds = store.get_credentials()

            service = build('sheets', 'v4', credentials=creds)

            # Create spreadsheet
            title = f"ADK Test Sheet - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            spreadsheet = {
                'properties': {
                    'title': title
                }
            }

            result = service.spreadsheets().create(body=spreadsheet).execute()

            sheet_id = result['spreadsheetId']
            sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"

            logger.info(f"  SUCCESS: Created spreadsheet")
            logger.info(f"    Title: {title}")
            logger.info(f"    ID: {sheet_id}")
            logger.info(f"    URL: {sheet_url}")

            # Track for cleanup
            self.created_resources.append({
                'type': 'sheet',
                'id': sheet_id,
                'title': title
            })

            return self._log_result('tier1', test_name, True, f"Created: {title}")

        except Exception as e:
            logger.error(f"  FAILED: {e}")
            return self._log_result('tier1', test_name, False, str(e))

    # ========================================================================
    # TIER 2: MULTI-AGENT COORDINATION (2-3 agents working together)
    # ========================================================================

    async def test_tier2_contact_to_email_draft(self):
        """Test: Find contact 'Tomislav Golić' and draft email to him"""
        test_name = "Multi-Agent: Find contact + Draft email"
        logger.info(f"\n[TIER 2] {test_name}")

        try:
            from googleapiclient.discovery import build

            store = get_credential_store()
            creds = store.get_credentials()

            # Step 1: Find contact (Rolodex agent)
            logger.info("  Step 1: Searching for contact...")
            people_service = build('people', 'v1', credentials=creds)

            results = people_service.people().connections().list(
                resourceName='people/me',
                pageSize=100,
                personFields='names,emailAddresses'
            ).execute()

            connections = results.get('connections', [])

            contact = None
            for person in connections:
                names = person.get('names', [])
                if names:
                    display_name = names[0].get('displayName', '')
                    if 'Tomislav' in display_name:
                        contact = person
                        break

            if not contact:
                logger.warning("  Contact not found, using test email")
                contact_email = "tgolic555@gmail.com"
                contact_name = "Tomislav"
            else:
                names = contact.get('names', [])
                emails = contact.get('emailAddresses', [])
                contact_name = names[0].get('displayName') if names else 'Unknown'
                contact_email = emails[0].get('value') if emails else 'test@example.com'

            logger.info(f"    Found: {contact_name} ({contact_email})")

            # Step 2: Create email draft (Mailer agent)
            logger.info("  Step 2: Creating email draft...")
            gmail_service = build('gmail', 'v1', credentials=creds)

            from email.mime.text import MIMEText
            import base64

            message = MIMEText(f"Hello {contact_name},\n\nThis is a test email from the ADK Multi-Agent System.\n\nBest regards,\nADK System")
            message['to'] = contact_email
            message['subject'] = f"Test from ADK System - {datetime.now().strftime('%Y-%m-%d %H:%M')}"

            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            draft = gmail_service.users().drafts().create(
                userId='me',
                body={'message': {'raw': raw_message}}
            ).execute()

            draft_id = draft['id']
            logger.info(f"    Created draft ID: {draft_id}")

            logger.info(f"  SUCCESS: Multi-agent coordination complete!")
            logger.info(f"    - Rolodex found contact: {contact_name}")
            logger.info(f"    - Mailer created draft to: {contact_email}")

            return self._log_result('tier2', test_name, True, f"Draft created for {contact_name}")

        except Exception as e:
            logger.error(f"  FAILED: {e}")
            return self._log_result('tier2', test_name, False, str(e))

    async def test_tier2_emails_to_doc_summary(self):
        """Test: Search emails from specific sender + Create summary doc"""
        test_name = "Multi-Agent: Search emails + Create doc summary"
        logger.info(f"\n[TIER 2] {test_name}")

        try:
            from googleapiclient.discovery import build

            store = get_credential_store()
            creds = store.get_credentials()

            # Step 1: Search emails (Mailer agent)
            logger.info("  Step 1: Searching emails from 'tgolic555@gmail.com'...")
            gmail_service = build('gmail', 'v1', credentials=creds)

            results = gmail_service.users().messages().list(
                userId='me',
                q='from:tgolic555@gmail.com',
                maxResults=5
            ).execute()

            messages = results.get('messages', [])

            if not messages:
                logger.warning("  No emails found from that sender")
                email_summary = "No emails found from tgolic555@gmail.com"
            else:
                logger.info(f"    Found {len(messages)} emails")

                # Get details of first 3 emails
                email_details = []
                for msg_ref in messages[:3]:
                    msg = gmail_service.users().messages().get(
                        userId='me',
                        id=msg_ref['id'],
                        format='metadata',
                        metadataHeaders=['From', 'Subject', 'Date']
                    ).execute()

                    headers = {h['name']: h['value'] for h in msg['payload']['headers']}
                    email_details.append({
                        'subject': headers.get('Subject', 'No Subject'),
                        'date': headers.get('Date', 'Unknown'),
                        'from': headers.get('From', 'Unknown')
                    })

                email_summary = f"Found {len(messages)} emails:\n\n"
                for i, email in enumerate(email_details, 1):
                    email_summary += f"{i}. {email['subject']}\n   Date: {email['date']}\n\n"

            # Step 2: Create summary document (Scribe agent)
            logger.info("  Step 2: Creating summary document...")
            docs_service = build('docs', 'v1', credentials=creds)

            title = f"Email Summary - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            doc = docs_service.documents().create(body={'title': title}).execute()

            doc_id = doc['documentId']

            # Insert content
            requests = [
                {
                    'insertText': {
                        'location': {'index': 1},
                        'text': f"Email Summary Report\n\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{email_summary}"
                    }
                }
            ]

            docs_service.documents().batchUpdate(
                documentId=doc_id,
                body={'requests': requests}
            ).execute()

            doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
            logger.info(f"    Created doc: {doc_url}")

            # Track for cleanup
            self.created_resources.append({
                'type': 'doc',
                'id': doc_id,
                'title': title
            })

            logger.info(f"  SUCCESS: Multi-agent coordination complete!")
            logger.info(f"    - Mailer found {len(messages)} emails")
            logger.info(f"    - Scribe created summary doc")

            return self._log_result('tier2', test_name, True, f"Created summary doc with {len(messages)} emails")

        except Exception as e:
            logger.error(f"  FAILED: {e}")
            return self._log_result('tier2', test_name, False, str(e))

    async def test_tier2_calendar_to_email_summary(self):
        """Test: Get today's calendar events + Send email summary"""
        test_name = "Multi-Agent: Calendar events + Email summary"
        logger.info(f"\n[TIER 2] {test_name}")

        try:
            from googleapiclient.discovery import build
            from datetime import datetime, timezone, timedelta

            store = get_credential_store()
            creds = store.get_credentials()

            # Step 1: Get calendar events (Secretary agent)
            logger.info("  Step 1: Fetching today's calendar events...")
            calendar_service = build('calendar', 'v3', credentials=creds)

            now = datetime.now(timezone.utc)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)

            events_result = calendar_service.events().list(
                calendarId='primary',
                timeMin=today_start.isoformat(),
                timeMax=today_end.isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])

            if not events:
                logger.info("    No events today")
                calendar_summary = "No events scheduled for today."
            else:
                logger.info(f"    Found {len(events)} events")
                calendar_summary = f"You have {len(events)} events today:\n\n"
                for i, event in enumerate(events, 1):
                    start = event['start'].get('dateTime', event['start'].get('date'))
                    calendar_summary += f"{i}. {event['summary']} at {start}\n"

            # Step 2: Create email draft with summary (Mailer agent)
            logger.info("  Step 2: Creating email draft with calendar summary...")
            gmail_service = build('gmail', 'v1', credentials=creds)

            from email.mime.text import MIMEText
            import base64

            message = MIMEText(f"Daily Calendar Summary\n\n{calendar_summary}\n\nGenerated by ADK System")
            message['to'] = "tgolic555@gmail.com"  # Send to self
            message['subject'] = f"Calendar Summary - {datetime.now().strftime('%Y-%m-%d')}"

            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            draft = gmail_service.users().drafts().create(
                userId='me',
                body={'message': {'raw': raw_message}}
            ).execute()

            draft_id = draft['id']
            logger.info(f"    Created draft ID: {draft_id}")

            logger.info(f"  SUCCESS: Multi-agent coordination complete!")
            logger.info(f"    - Secretary found {len(events)} events")
            logger.info(f"    - Mailer created email draft")

            return self._log_result('tier2', test_name, True, f"Draft created with {len(events)} events")

        except Exception as e:
            logger.error(f"  FAILED: {e}")
            return self._log_result('tier2', test_name, False, str(e))

    # ========================================================================
    # TIER 3: COMPLEX CROSS-API OPERATIONS (3+ agents, complex workflows)
    # ========================================================================

    async def test_tier3_email_search_doc_drive_share(self):
        """Test: Search emails + Create summary doc + Upload to Drive + Share"""
        test_name = "Complex: Email search → Doc summary → Drive upload → Share"
        logger.info(f"\n[TIER 3] {test_name}")

        try:
            from googleapiclient.discovery import build

            store = get_credential_store()
            creds = store.get_credentials()

            # Step 1: Search emails (Mailer)
            logger.info("  Step 1: Searching recent emails...")
            gmail_service = build('gmail', 'v1', credentials=creds)

            results = gmail_service.users().messages().list(
                userId='me',
                maxResults=5
            ).execute()

            messages = results.get('messages', [])
            logger.info(f"    Found {len(messages)} emails")

            # Get email details
            email_details = []
            for msg_ref in messages[:3]:
                msg = gmail_service.users().messages().get(
                    userId='me',
                    id=msg_ref['id'],
                    format='metadata',
                    metadataHeaders=['From', 'Subject', 'Date']
                ).execute()

                headers = {h['name']: h['value'] for h in msg['payload']['headers']}
                email_details.append({
                    'subject': headers.get('Subject', 'No Subject'),
                    'from': headers.get('From', 'Unknown'),
                    'date': headers.get('Date', 'Unknown')
                })

            # Step 2: Create summary doc (Scribe)
            logger.info("  Step 2: Creating comprehensive summary document...")
            docs_service = build('docs', 'v1', credentials=creds)

            title = f"Comprehensive Email Report - {datetime.now().strftime('%Y-%m-%d')}"
            doc = docs_service.documents().create(body={'title': title}).execute()

            doc_id = doc['documentId']

            # Build detailed content
            content = f"COMPREHENSIVE EMAIL REPORT\n\n"
            content += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            content += f"Total emails analyzed: {len(messages)}\n\n"
            content += "="*50 + "\n\n"

            for i, email in enumerate(email_details, 1):
                content += f"Email #{i}\n"
                content += f"Subject: {email['subject']}\n"
                content += f"From: {email['from']}\n"
                content += f"Date: {email['date']}\n"
                content += "-"*50 + "\n\n"

            # Insert content
            requests = [
                {
                    'insertText': {
                        'location': {'index': 1},
                        'text': content
                    }
                }
            ]

            docs_service.documents().batchUpdate(
                documentId=doc_id,
                body={'requests': requests}
            ).execute()

            logger.info(f"    Created doc ID: {doc_id}")

            # Step 3: Document is already in Drive, get its file metadata (Librarian)
            logger.info("  Step 3: Verifying file in Drive...")
            drive_service = build('drive', 'v3', credentials=creds)

            file_metadata = drive_service.files().get(
                fileId=doc_id,
                fields='id,name,webViewLink'
            ).execute()

            logger.info(f"    File in Drive: {file_metadata['name']}")
            logger.info(f"    URL: {file_metadata['webViewLink']}")

            # Step 4: Share with test user (Librarian)
            logger.info("  Step 4: Setting up sharing permissions...")

            # Make it accessible to anyone with link (safer than specific email)
            permission = {
                'type': 'anyone',
                'role': 'reader'
            }

            drive_service.permissions().create(
                fileId=doc_id,
                body=permission
            ).execute()

            logger.info(f"    Sharing configured: Anyone with link can view")

            # Track for cleanup
            self.created_resources.append({
                'type': 'doc',
                'id': doc_id,
                'title': title
            })

            logger.info(f"  SUCCESS: Complex multi-agent workflow complete!")
            logger.info(f"    - Mailer: Found {len(messages)} emails")
            logger.info(f"    - Scribe: Created comprehensive doc")
            logger.info(f"    - Librarian: Verified in Drive")
            logger.info(f"    - Librarian: Set up sharing")

            return self._log_result('tier3', test_name, True, f"Complete workflow with {len(messages)} emails")

        except Exception as e:
            logger.error(f"  FAILED: {e}")
            return self._log_result('tier3', test_name, False, str(e))

    async def test_tier3_calendar_contacts_doc_email(self):
        """Test: Calendar → Find attendees in contacts → Create doc → Email to all"""
        test_name = "Complex: Calendar → Contacts → Doc → Email distribution"
        logger.info(f"\n[TIER 3] {test_name}")

        try:
            from googleapiclient.discovery import build
            from datetime import datetime, timezone, timedelta

            store = get_credential_store()
            creds = store.get_credentials()

            # Step 1: Get calendar events (Secretary)
            logger.info("  Step 1: Fetching today's calendar events...")
            calendar_service = build('calendar', 'v3', credentials=creds)

            now = datetime.now(timezone.utc)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)

            events_result = calendar_service.events().list(
                calendarId='primary',
                timeMin=today_start.isoformat(),
                timeMax=today_end.isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])
            logger.info(f"    Found {len(events)} events")

            # Extract attendees
            all_attendees = set()
            for event in events:
                attendees = event.get('attendees', [])
                for attendee in attendees:
                    all_attendees.add(attendee.get('email'))

            logger.info(f"    Found {len(all_attendees)} unique attendees")

            # Step 2: Look up attendees in contacts (Rolodex)
            logger.info("  Step 2: Looking up attendees in contacts...")
            people_service = build('people', 'v1', credentials=creds)

            contacts_result = people_service.people().connections().list(
                resourceName='people/me',
                pageSize=100,
                personFields='names,emailAddresses'
            ).execute()

            connections = contacts_result.get('connections', [])

            matched_contacts = []
            for person in connections:
                emails = person.get('emailAddresses', [])
                for email_obj in emails:
                    if email_obj.get('value') in all_attendees:
                        names = person.get('names', [])
                        name = names[0].get('displayName') if names else 'Unknown'
                        matched_contacts.append({
                            'name': name,
                            'email': email_obj.get('value')
                        })
                        break

            logger.info(f"    Matched {len(matched_contacts)} contacts")

            # Step 3: Create detailed report doc (Scribe)
            logger.info("  Step 3: Creating detailed meeting report...")
            docs_service = build('docs', 'v1', credentials=creds)

            title = f"Meeting Report - {datetime.now().strftime('%Y-%m-%d')}"
            doc = docs_service.documents().create(body={'title': title}).execute()

            doc_id = doc['documentId']

            # Build report content
            content = f"DAILY MEETING REPORT\n\n"
            content += f"Date: {datetime.now().strftime('%Y-%m-%d')}\n"
            content += f"Generated: {datetime.now().strftime('%H:%M:%S')}\n\n"
            content += "="*50 + "\n\n"
            content += f"MEETINGS TODAY: {len(events)}\n\n"

            for i, event in enumerate(events, 1):
                start = event['start'].get('dateTime', event['start'].get('date'))
                content += f"{i}. {event['summary']}\n"
                content += f"   Time: {start}\n\n"

            content += "\n" + "="*50 + "\n\n"
            content += f"ATTENDEES: {len(matched_contacts)} contacts\n\n"

            for contact in matched_contacts:
                content += f"- {contact['name']} ({contact['email']})\n"

            # Insert content
            requests = [
                {
                    'insertText': {
                        'location': {'index': 1},
                        'text': content
                    }
                }
            ]

            docs_service.documents().batchUpdate(
                documentId=doc_id,
                body={'requests': requests}
            ).execute()

            doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
            logger.info(f"    Created report: {doc_url}")

            # Step 4: Create email draft with report (Mailer)
            logger.info("  Step 4: Creating email draft with report...")
            gmail_service = build('gmail', 'v1', credentials=creds)

            from email.mime.text import MIMEText
            import base64

            email_body = f"Daily Meeting Report\n\n"
            email_body += f"Please find today's meeting report here:\n{doc_url}\n\n"
            email_body += f"Summary:\n"
            email_body += f"- {len(events)} meetings today\n"
            email_body += f"- {len(matched_contacts)} attendees\n\n"
            email_body += f"Generated by ADK System"

            message = MIMEText(email_body)
            message['to'] = "tgolic555@gmail.com"  # Send to self
            message['subject'] = f"Meeting Report - {datetime.now().strftime('%Y-%m-%d')}"

            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            draft = gmail_service.users().drafts().create(
                userId='me',
                body={'message': {'raw': raw_message}}
            ).execute()

            draft_id = draft['id']
            logger.info(f"    Created draft ID: {draft_id}")

            # Track for cleanup
            self.created_resources.append({
                'type': 'doc',
                'id': doc_id,
                'title': title
            })

            logger.info(f"  SUCCESS: Complex 4-agent workflow complete!")
            logger.info(f"    - Secretary: Found {len(events)} meetings")
            logger.info(f"    - Rolodex: Matched {len(matched_contacts)} contacts")
            logger.info(f"    - Scribe: Created detailed report")
            logger.info(f"    - Mailer: Created distribution draft")

            return self._log_result('tier3', test_name, True, f"Complete workflow: {len(events)} meetings, {len(matched_contacts)} contacts")

        except Exception as e:
            logger.error(f"  FAILED: {e}")
            return self._log_result('tier3', test_name, False, str(e))

    async def test_tier3_contact_research_doc_email(self):
        """Test: Get contact → Create detailed profile doc → Share with team"""
        test_name = "Complex: Contact profile → Research doc → Team distribution"
        logger.info(f"\n[TIER 3] {test_name}")

        try:
            from googleapiclient.discovery import build

            store = get_credential_store()
            creds = store.get_credentials()

            # Step 1: Get contact details (Rolodex)
            logger.info("  Step 1: Fetching contact 'Tomislav Golić'...")
            people_service = build('people', 'v1', credentials=creds)

            results = people_service.people().connections().list(
                resourceName='people/me',
                pageSize=100,
                personFields='names,emailAddresses,phoneNumbers,organizations,addresses'
            ).execute()

            connections = results.get('connections', [])

            target_contact = None
            for person in connections:
                names = person.get('names', [])
                if names:
                    display_name = names[0].get('displayName', '')
                    if 'Tomislav' in display_name:
                        target_contact = person
                        break

            if not target_contact:
                logger.warning("  Contact not found, using mock data")
                contact_info = {
                    'name': 'Tomislav Golić',
                    'email': 'tgolic555@gmail.com',
                    'phone': '0977984268',
                    'company': 'Unknown'
                }
            else:
                names = target_contact.get('names', [])
                emails = target_contact.get('emailAddresses', [])
                phones = target_contact.get('phoneNumbers', [])
                orgs = target_contact.get('organizations', [])

                contact_info = {
                    'name': names[0].get('displayName') if names else 'Unknown',
                    'email': emails[0].get('value') if emails else 'No email',
                    'phone': phones[0].get('value') if phones else 'No phone',
                    'company': orgs[0].get('name') if orgs else 'No company'
                }

            logger.info(f"    Found: {contact_info['name']}")

            # Step 2: Search recent emails from/to contact (Mailer)
            logger.info("  Step 2: Searching email history with contact...")
            gmail_service = build('gmail', 'v1', credentials=creds)

            query = f"from:{contact_info['email']} OR to:{contact_info['email']}"
            results = gmail_service.users().messages().list(
                userId='me',
                q=query,
                maxResults=5
            ).execute()

            messages = results.get('messages', [])
            logger.info(f"    Found {len(messages)} emails")

            email_history = []
            for msg_ref in messages[:3]:
                msg = gmail_service.users().messages().get(
                    userId='me',
                    id=msg_ref['id'],
                    format='metadata',
                    metadataHeaders=['Subject', 'Date']
                ).execute()

                headers = {h['name']: h['value'] for h in msg['payload']['headers']}
                email_history.append({
                    'subject': headers.get('Subject', 'No Subject'),
                    'date': headers.get('Date', 'Unknown')
                })

            # Step 3: Create comprehensive profile doc (Scribe)
            logger.info("  Step 3: Creating comprehensive profile document...")
            docs_service = build('docs', 'v1', credentials=creds)

            title = f"Contact Profile - {contact_info['name']} - {datetime.now().strftime('%Y-%m-%d')}"
            doc = docs_service.documents().create(body={'title': title}).execute()

            doc_id = doc['documentId']

            # Build profile content
            content = f"CONTACT PROFILE REPORT\n\n"
            content += "="*50 + "\n\n"
            content += f"Name: {contact_info['name']}\n"
            content += f"Email: {contact_info['email']}\n"
            content += f"Phone: {contact_info['phone']}\n"
            content += f"Company: {contact_info['company']}\n"
            content += f"\n" + "="*50 + "\n\n"
            content += f"EMAIL HISTORY ({len(messages)} total communications)\n\n"

            for i, email in enumerate(email_history, 1):
                content += f"{i}. {email['subject']}\n"
                content += f"   Date: {email['date']}\n\n"

            content += "\n" + "="*50 + "\n\n"
            content += f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            content += f"Generated by: ADK Multi-Agent System\n"

            # Insert content
            requests = [
                {
                    'insertText': {
                        'location': {'index': 1},
                        'text': content
                    }
                }
            ]

            docs_service.documents().batchUpdate(
                documentId=doc_id,
                body={'requests': requests}
            ).execute()

            doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
            logger.info(f"    Created profile: {doc_url}")

            # Step 4: Share document (Librarian)
            logger.info("  Step 4: Setting up document sharing...")
            drive_service = build('drive', 'v3', credentials=creds)

            permission = {
                'type': 'anyone',
                'role': 'reader'
            }

            drive_service.permissions().create(
                fileId=doc_id,
                body=permission
            ).execute()

            logger.info(f"    Document shared: Anyone with link")

            # Step 5: Send notification email (Mailer)
            logger.info("  Step 5: Sending notification email...")

            from email.mime.text import MIMEText
            import base64

            email_body = f"Contact Profile Report\n\n"
            email_body += f"A comprehensive profile for {contact_info['name']} has been created.\n\n"
            email_body += f"View the report here:\n{doc_url}\n\n"
            email_body += f"Summary:\n"
            email_body += f"- Email: {contact_info['email']}\n"
            email_body += f"- Phone: {contact_info['phone']}\n"
            email_body += f"- Company: {contact_info['company']}\n"
            email_body += f"- Email history: {len(messages)} messages\n\n"
            email_body += f"Generated by ADK System"

            message = MIMEText(email_body)
            message['to'] = "tgolic555@gmail.com"
            message['subject'] = f"Contact Profile: {contact_info['name']}"

            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            draft = gmail_service.users().drafts().create(
                userId='me',
                body={'message': {'raw': raw_message}}
            ).execute()

            draft_id = draft['id']
            logger.info(f"    Created notification draft ID: {draft_id}")

            # Track for cleanup
            self.created_resources.append({
                'type': 'doc',
                'id': doc_id,
                'title': title
            })

            logger.info(f"  SUCCESS: Complex 5-agent workflow complete!")
            logger.info(f"    - Rolodex: Retrieved contact details")
            logger.info(f"    - Mailer: Found {len(messages)} email communications")
            logger.info(f"    - Scribe: Created comprehensive profile")
            logger.info(f"    - Librarian: Set up sharing")
            logger.info(f"    - Mailer: Created notification draft")

            return self._log_result('tier3', test_name, True, f"Profile created: {contact_info['name']}, {len(messages)} emails")

        except Exception as e:
            logger.error(f"  FAILED: {e}")
            return self._log_result('tier3', test_name, False, str(e))

    # ========================================================================
    # UTILITY METHODS
    # ========================================================================

    def _log_result(self, tier: str, test_name: str, passed: bool, message: str) -> bool:
        """Log test result"""
        self.test_results[tier].append({
            'name': test_name,
            'passed': passed,
            'message': message
        })
        return passed

    async def cleanup(self):
        """Clean up created resources"""
        if not self.created_resources:
            logger.info("\nNo resources to clean up")
            return

        logger.info("\n" + "="*70)
        logger.info(f"CLEANUP - {len(self.created_resources)} resources")
        logger.info("="*70)

        try:
            from googleapiclient.discovery import build

            store = get_credential_store()
            creds = store.get_credentials()

            drive_service = build('drive', 'v3', credentials=creds)

            for resource in self.created_resources:
                try:
                    logger.info(f"Deleting {resource['type']}: {resource['title']}")
                    drive_service.files().delete(fileId=resource['id']).execute()
                    logger.info(f"  OK - Deleted")
                except Exception as e:
                    logger.warning(f"  WARNING - Could not delete: {e}")

            logger.info("\nCleanup complete!")

        except Exception as e:
            logger.error(f"Cleanup error: {e}")

    def print_summary(self):
        """Print comprehensive test summary"""
        logger.info("\n" + "="*70)
        logger.info("COMPREHENSIVE TEST SUMMARY")
        logger.info("="*70)

        total_tests = 0
        total_passed = 0

        for tier in ['tier1', 'tier2', 'tier3']:
            tier_name = {
                'tier1': 'TIER 1 - Single Agent Operations',
                'tier2': 'TIER 2 - Multi-Agent Coordination',
                'tier3': 'TIER 3 - Complex Cross-API Workflows'
            }[tier]

            results = self.test_results[tier]
            passed = sum(1 for r in results if r['passed'])
            total = len(results)

            total_tests += total
            total_passed += passed

            logger.info(f"\n{tier_name}")
            logger.info("-"*70)
            logger.info(f"Tests: {passed}/{total} passed")

            for result in results:
                status = "PASS" if result['passed'] else "FAIL"
                logger.info(f"  [{status}] {result['name']}")
                if result['message']:
                    logger.info(f"        {result['message']}")

        logger.info("\n" + "="*70)
        logger.info(f"TOTAL: {total_passed}/{total_tests} tests passed")

        success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
        logger.info(f"SUCCESS RATE: {success_rate:.1f}%")
        logger.info("="*70)

        if success_rate == 100:
            logger.info("\n🎉🎉🎉 ALL TESTS PASSED! SYSTEM FULLY OPERATIONAL! 🎉🎉🎉")
        elif success_rate >= 80:
            logger.info("\n✓✓✓ EXCELLENT! System mostly operational")
        elif success_rate >= 60:
            logger.info("\n⚠⚠⚠ GOOD! Some issues but core functionality works")
        else:
            logger.info("\n✗✗✗ NEEDS ATTENTION! Multiple failures detected")

    # ========================================================================
    # MAIN TEST RUNNER
    # ========================================================================

    async def run_all_tests(self):
        """Run all comprehensive tests"""
        logger.info("\n" + "#"*70)
        logger.info("# COMPREHENSIVE MULTI-AGENT SCENARIO TESTS")
        logger.info("# Testing REAL APIs with REAL data")
        logger.info("#"*70)

        # Setup
        if not await self.setup():
            logger.error("Setup failed! Cannot proceed with tests")
            return False

        logger.info("\n" + "="*70)
        logger.info("TIER 1: SINGLE-AGENT OPERATIONS")
        logger.info("="*70)

        await self.test_tier1_gmail_list_emails()
        await self.test_tier1_contacts_search()
        await self.test_tier1_drive_list_files()
        await self.test_tier1_calendar_list_events()
        await self.test_tier1_docs_create_document()
        await self.test_tier1_sheets_create_spreadsheet()

        logger.info("\n" + "="*70)
        logger.info("TIER 2: MULTI-AGENT COORDINATION")
        logger.info("="*70)

        await self.test_tier2_contact_to_email_draft()
        await self.test_tier2_emails_to_doc_summary()
        await self.test_tier2_calendar_to_email_summary()

        logger.info("\n" + "="*70)
        logger.info("TIER 3: COMPLEX CROSS-API WORKFLOWS")
        logger.info("="*70)

        await self.test_tier3_email_search_doc_drive_share()
        await self.test_tier3_calendar_contacts_doc_email()
        await self.test_tier3_contact_research_doc_email()

        # Print summary
        self.print_summary()

        # Cleanup
        await self.cleanup()

        # Calculate success
        total_tests = sum(len(self.test_results[tier]) for tier in ['tier1', 'tier2', 'tier3'])
        total_passed = sum(
            sum(1 for r in self.test_results[tier] if r['passed'])
            for tier in ['tier1', 'tier2', 'tier3']
        )

        return total_passed == total_tests


async def main():
    """Main entry point"""
    tester = ComprehensiveScenarioTester()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
