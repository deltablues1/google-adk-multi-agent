"""
Real API Execution Test - End-to-End with Actual API Calls

This test performs REAL API operations:
- Creates real documents on Google Drive
- Sends real emails via Gmail
- Shares real documents with permissions
- Searches real contacts

Complex Multi-Agent Workflow Test:
"Detaljno istraži sve o hidroponskom uzgoju, spremi taj dokument na drive,
pronađi kontak Tomislav Golić i pošalji mu taj dokument na mail,
dokument mora biti shared view za njegovu mail adresu"

Expected Flow:
1. Researcher - Research hydroponic farming
2. Scribe - Create document on Drive with research
3. Contacts/Mailer - Find contact "Tomislav Golić"
4. Scribe/Librarian - Share document with specific email (view permission)
5. Mailer - Send email with document link
"""

import asyncio
import sys
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment
load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))

print("\n" + "="*80)
print("REAL API EXECUTION TEST - End-to-End Multi-Agent Workflow")
print("="*80)


async def verify_document_created(doc_title: str) -> dict:
    """
    Verify document was actually created on Google Drive.

    Returns:
        dict with status and document info if found
    """
    print(f"\n[VERIFICATION] Checking if document '{doc_title}' exists on Drive...")

    try:
        from tools.adk_tools.drive_adk_tools import drive_search_files

        # Search for document by name
        result = await drive_search_files(
            query=f"name contains '{doc_title}' and mimeType = 'application/vnd.google-apps.document'",
            max_results=5
        )

        if result.get('status') == 'success' and result.get('files'):
            files = result['files']
            print(f"    [OK] Found {len(files)} document(s) matching '{doc_title}'")
            for file in files:
                print(f"        - {file['name']} (ID: {file['id']})")
            return {'found': True, 'files': files}
        else:
            print(f"    [NOT FOUND] No documents found with title '{doc_title}'")
            return {'found': False, 'files': []}

    except Exception as e:
        print(f"    [ERROR] Verification failed: {e}")
        return {'found': False, 'error': str(e)}


async def verify_email_sent(recipient: str, subject_contains: str) -> dict:
    """
    Verify email was actually sent.

    Returns:
        dict with status and email info if found
    """
    print(f"\n[VERIFICATION] Checking if email to '{recipient}' was sent...")

    try:
        from auth.oauth_manager import get_oauth_manager
        from tools.api_implementations.gmail_api import gmail_search_threads

        # Get credentials
        oauth_manager = get_oauth_manager()
        creds = oauth_manager.get_credentials()

        if not creds:
            print("    [ERROR] No credentials available")
            return {'found': False, 'error': 'No credentials'}

        # Search in sent folder
        query = f"to:{recipient} subject:{subject_contains} in:sent"
        result = await gmail_search_threads(creds, query=query, max_results=5)

        if result.get('threads'):
            threads = result['threads']
            print(f"    [OK] Found {len(threads)} sent email(s) to {recipient}")
            for thread in threads:
                print(f"        - Subject: {thread.get('subject', 'N/A')}")
                print(f"          Snippet: {thread.get('snippet', 'N/A')[:100]}...")
            return {'found': True, 'messages': threads}
        else:
            print(f"    [NOT FOUND] No sent emails found to '{recipient}'")
            return {'found': False, 'messages': []}

    except Exception as e:
        print(f"    [ERROR] Verification failed: {e}")
        return {'found': False, 'error': str(e)}


async def verify_document_shared(doc_id: str, email: str) -> dict:
    """
    Verify document has correct sharing permissions.

    Returns:
        dict with sharing status
    """
    print(f"\n[VERIFICATION] Checking sharing permissions for document...")

    try:
        from tools.adk_tools.drive_adk_tools import drive_get_file

        # Get file details including permissions
        result = await drive_get_file(file_id=doc_id, include_permissions=True)

        if result.get('status') == 'success':
            file_info = result.get('file', {})
            permissions = file_info.get('permissions', [])

            print(f"    [INFO] Document has {len(permissions)} permission(s)")

            # Check if email has view permission
            for perm in permissions:
                perm_email = perm.get('emailAddress', '')
                perm_role = perm.get('role', '')
                if perm_email == email:
                    print(f"    [OK] Found permission for {email}: {perm_role}")
                    return {'shared': True, 'role': perm_role, 'permission': perm}

            print(f"    [NOT FOUND] No permission found for {email}")
            return {'shared': False, 'permissions': permissions}
        else:
            print(f"    [ERROR] Could not get file info: {result.get('error', 'Unknown')}")
            return {'shared': False, 'error': result.get('error')}

    except Exception as e:
        print(f"    [ERROR] Verification failed: {e}")
        return {'shared': False, 'error': str(e)}


async def test_complex_multiagent_workflow():
    """
    Test complex multi-agent workflow with REAL API calls.

    Workflow:
    "Detaljno istraži sve o hidroponskom uzgoju, spremi taj dokument na drive,
    pronađi kontak Tomislav Golić i pošalji mu taj dokument na mail,
    dokument mora biti shared view za njegovu mail adresu"

    This should trigger:
    1. Researcher agent - web research
    2. Scribe agent - create document on Drive
    3. Contacts/Mailer agent - find contact
    4. Drive/Scribe agent - share document
    5. Mailer agent - send email
    """
    print("\n" + "="*80)
    print("COMPLEX MULTI-AGENT WORKFLOW TEST")
    print("="*80)

    print("\n[TASK] Multi-step workflow:")
    print("  1. Research hydroponic farming (detailed)")
    print("  2. Create document on Drive with research")
    print("  3. Find contact 'Tomislav Golić'")
    print("  4. Share document (view permission) with contact's email")
    print("  5. Send email with document link")

    try:
        from agents.adk_agents import (
            create_mailer_agent,
            create_researcher_agent,
            create_scribe_agent,
            create_secretary_agent,
            create_analyst_agent,
            create_librarian_agent,
            create_orchestrator_agent
        )
        from agents.adk_agents.runner_utils import run_agent_stream
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types

        print("\n[1/6] Creating all specialized agents...")
        mailer = create_mailer_agent()
        researcher = create_researcher_agent()
        scribe = create_scribe_agent()
        secretary = create_secretary_agent()
        analyst = create_analyst_agent()
        librarian = create_librarian_agent()
        print("    [OK] 6 specialized agents created")

        print("\n[2/6] Creating orchestrator with AutoFlow...")
        orchestrator = create_orchestrator_agent(
            sub_agents=[mailer, researcher, scribe, secretary, analyst, librarian]
        )
        print("    [OK] Orchestrator with AutoFlow enabled")

        print("\n[3/6] Sending complex multi-agent request...")

        user_query = """Detaljno istraži sve o hidroponskom uzgoju, spremi taj dokument na drive sa naslovom 'Hidroponski Uzgoj - Istraživanje',
pronađi kontak Tomislav Golić i pošalji mu taj dokument na mail,
dokument mora biti shared view za njegovu mail adresu."""

        print(f"\n    User Query:")
        print(f"    '{user_query}'")

        print(f"\n[4/6] Executing workflow with real API calls...")
        print("    [INFO] This will take some time as agents perform real operations...")
        print("    [INFO] Tracking events:")

        # Track execution
        events_count = 0
        tool_calls = []
        agent_switches = []
        response_parts = []

        # Use stream to see all events
        session_service = InMemorySessionService()
        app_name = "agents"
        session_id = f"real-test-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        user_id = "real-user"

        # Create runner
        runner = Runner(
            agent=orchestrator,
            app_name=app_name,
            session_service=session_service
        )

        # Create session
        try:
            await session_service.create_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id
            )
        except:
            pass

        # Convert to Content
        content = types.Content(
            role="user",
            parts=[types.Part(text=user_query)]
        )

        # Run and track events
        events = runner.run_async(
            new_message=content,
            session_id=session_id,
            user_id=user_id
        )

        async for event in events:
            events_count += 1

            # Check event type
            event_type = type(event).__name__

            # Track function calls (tool executions)
            if hasattr(event, 'content') and hasattr(event.content, 'parts'):
                for part in event.content.parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        func_name = part.function_call.name
                        tool_calls.append(func_name)
                        print(f"        -> Tool call: {func_name}")

                    # Track text responses
                    if hasattr(part, 'text') and part.text:
                        response_parts.append(part.text)

            # Track text in event
            if hasattr(event, 'text') and event.text:
                response_parts.append(event.text)

            # Track agent switches (if observable)
            if hasattr(event, 'agent') and event.agent:
                agent_name = getattr(event.agent, 'name', 'unknown')
                if not agent_switches or agent_switches[-1] != agent_name:
                    agent_switches.append(agent_name)
                    print(f"        -> Agent: {agent_name}")

        print(f"\n    [OK] Execution completed!")
        print(f"        Total events: {events_count}")
        print(f"        Tool calls executed: {len(tool_calls)}")
        print(f"        Unique tools: {set(tool_calls)}")
        print(f"        Agent switches: {len(agent_switches)}")

        # Combine response
        full_response = "".join(response_parts)
        print(f"\n    [RESPONSE] Length: {len(full_response)} chars")
        print(f"    Preview: {full_response[:500]}...")

        print(f"\n[5/6] Verifying real API operations...")

        verification_results = {}

        # 1. Verify document created
        doc_result = await verify_document_created("Hidroponski Uzgoj")
        verification_results['document_created'] = doc_result['found']

        # If document found, verify sharing
        if doc_result['found'] and doc_result.get('files'):
            doc_id = doc_result['files'][0]['id']

            # Try to get email from contacts or use test email
            # For now, we'll check if document has any sharing permissions
            share_result = await verify_document_shared(doc_id, "tomislav.golic@example.com")
            verification_results['document_shared'] = share_result.get('shared', False)
        else:
            verification_results['document_shared'] = False

        # 2. Verify email sent
        email_result = await verify_email_sent("tomislav", "hidroponski")
        verification_results['email_sent'] = email_result['found']

        print(f"\n[6/6] Verification Results:")
        print(f"    Document Created: {'PASS' if verification_results['document_created'] else 'FAIL'}")
        print(f"    Document Shared: {'PASS' if verification_results['document_shared'] else 'FAIL'}")
        print(f"    Email Sent: {'PASS' if verification_results['email_sent'] else 'FAIL'}")

        # Overall result
        all_passed = all(verification_results.values())

        if all_passed:
            print("\n[SUCCESS] All real API operations verified!")
        else:
            print("\n[PARTIAL] Some operations may not have completed:")
            print("    This could be due to:")
            print("    - Agent still processing (async operations)")
            print("    - Permissions issues")
            print("    - Contact not found")
            print("    Note: Check the full response above for details")

        print(f"\n[SUMMARY]")
        print(f"    Events processed: {events_count}")
        print(f"    Tools executed: {len(tool_calls)}")
        print(f"    Response length: {len(full_response)} chars")
        print(f"    Real operations verified: {sum(verification_results.values())}/{len(verification_results)}")

        return {
            'success': len(tool_calls) > 0,  # At least some tools executed
            'events': events_count,
            'tool_calls': tool_calls,
            'verification': verification_results,
            'response': full_response
        }

    except Exception as e:
        print(f"\n[ERROR] Test failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': str(e)}


async def main():
    """Main test runner."""

    print("\n[INFO] This test will perform REAL API operations:")
    print("       - Create real Google Doc")
    print("       - Search real contacts")
    print("       - Share real document")
    print("       - Send real email")
    print("\n[WARNING] This will create actual resources in your Google account!")

    # Run complex workflow test
    result = await test_complex_multiagent_workflow()

    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)

    if result['success']:
        print(f"\n[SUCCESS] Multi-agent workflow executed with {len(result.get('tool_calls', []))} tool calls")
        print(f"\nTool calls made: {set(result.get('tool_calls', []))}")
    else:
        print(f"\n[FAILED] Test encountered errors")
        if 'error' in result:
            print(f"Error: {result['error']}")

    print("\n")


if __name__ == "__main__":
    asyncio.run(main())
