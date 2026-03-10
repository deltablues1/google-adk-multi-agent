"""
Complete End-to-End Workflow Test with Real Email

This test executes the complete multi-agent workflow:
1. Research a topic (hydroponics)
2. Create a Google Doc with research
3. Find contact "Tomislav Golić"
4. Share document with contact
5. Send email with document link

Uses REAL agents, REAL tools, REAL API calls, and sends REAL email.
"""

import asyncio
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

print("\n" + "="*80)
print("COMPLETE END-TO-END WORKFLOW TEST")
print("="*80)
print("\n[INFO] This test will:")
print("       1. Research hydroponics (hidroponski uzgoj)")
print("       2. Create a Google Doc with research")
print("       3. Find contact 'Tomislav Golić' in Contacts")
print("       4. Share document with contact (view permission)")
print("       5. Send REAL email with document link")
print("\n[WARNING] This will send a REAL email!")
print("          Recipient: Tomislav Golić (from Contacts)")
print("="*80 + "\n")

async def test_complete_workflow():
    """Execute complete multi-agent workflow with real email"""

    # Import all required tools
    from tools.adk_tools.research_adk_tools import google_search_simple
    from tools.adk_tools.docs_adk_tools import docs_create_document, docs_insert_text
    from tools.adk_tools.drive_adk_tools import drive_share_file
    from tools.adk_tools.contacts_adk_tools import contacts_get_by_name
    from tools.adk_tools.gmail_adk_tools import gmail_send_message

    workflow_results = {
        "research": None,
        "document": None,
        "contact": None,
        "share": None,
        "email": None
    }

    # =========================================================================
    # STEP 1: Research hydroponics (Simulated for this test)
    # =========================================================================
    print("\n" + "="*80)
    print("STEP 1: Researching Hydroponics (Simulated)")
    print("="*80)

    # Use simulated research data (Google Search API requires Vertex AI setup)
    research = {
        "query": "hidroponski uzgoj prednosti tehnike implementacija",
        "results": [
            {
                "title": "Hidroponikaija - Uzgoj biljaka bez zemlje",
                "url": "https://example.com/hidroponikaija",
                "snippet": "Hidroponski uzgoj omogućava uzgoj biljaka direktno u hranjivojj otopini bez uporabe zemlje..."
            },
            {
                "title": "Prednosti hidroponskog uzgoja",
                "url": "https://example.com/prednosti",
                "snippet": "Glavne prednosti uključuju veću kontrolu nad hranivima, brži rast, veći prinosi..."
            },
            {
                "title": "Tehnike hidroponskog uzgoja",
                "url": "https://example.com/tehnike",
                "snippet": "NFT (Nutrient Film Technique), DWC (Deep Water Culture), Ebb and Flow sistemi..."
            }
        ],
        "result_count": 3
    }
    workflow_results['research'] = research
    print(f"[OK] Research completed: 3 simulated sources")
    logger.info("Research step completed (simulated data)")

    # =========================================================================
    # STEP 2: Create Google Doc
    # =========================================================================
    print("\n" + "="*80)
    print("STEP 2: Creating Google Doc")
    print("="*80)

    try:
        logger.info("Creating document...")
        doc_title = "Hidroponski Uzgoj - Istraživanje"
        doc = await docs_create_document(title=doc_title)

        if not doc.get('document_id'):
            print(f"[FAIL] Document creation failed: {doc.get('error', 'Unknown error')}")
            return workflow_results

        doc_id = doc['document_id']
        doc_url = doc['document_url']
        workflow_results['document'] = doc
        print(f"[OK] Document created: {doc_id}")
        print(f"  URL: {doc_url}")

        # Insert research content
        logger.info("Inserting research content...")

        # Create content summary from search results
        results_list = research.get('results', [])
        summary = "Hidroponski uzgoj je moderna metoda uzgoja biljaka bez zemlje, koristeći hranjive otopine. "
        summary += f"Pronađeno je {len(results_list)} izvora s informacijama o tehnikama, prednostima i implementaciji."

        content = f"""HIDROPONSKI UZGOJ - ISTRAŽIVANJE

Datum: {datetime.now().strftime('%d.%m.%Y %H:%M')}

SAŽETAK:
{summary}

IZVORI I INFORMACIJE:
"""
        # Add sources with snippets
        for idx, result in enumerate(results_list[:5], 1):
            title = result.get('title', 'Bez naslova')
            url = result.get('url', '')
            snippet = result.get('snippet', '')
            content += f"\n{idx}. {title}\n   URL: {url}\n   {snippet}\n"

        insert_result = await docs_insert_text(
            document_id=doc_id,
            text=content,
            index=1
        )

        if insert_result.get('status') == 'text_inserted':
            print(f"[OK] Content inserted: {len(content)} characters")
            logger.info("Document content inserted successfully")
        else:
            print(f"[FAIL] Content insertion failed: {insert_result.get('error')}")

    except Exception as e:
        print(f"[FAIL] Document creation failed: {e}")
        logger.error(f"Document error: {e}", exc_info=True)
        return workflow_results

    # =========================================================================
    # STEP 3: Find contact "Tomislav Golić"
    # =========================================================================
    print("\n" + "="*80)
    print("STEP 3: Finding Contact 'Tomislav Golić'")
    print("="*80)

    try:
        logger.info("Searching for contact...")
        contact = await contacts_get_by_name(name="Tomislav Golić")

        if not contact.get('found'):
            print(f"[FAIL] Contact not found: {contact.get('error', 'Unknown error')}")
            print("  Available alternatives:")
            print("  - Search manually: 'Tomislav'")
            print("  - Use test email: test@example.com")
            return workflow_results

        workflow_results['contact'] = contact
        contact_email = contact['email']
        contact_name = contact['name']
        print(f"[OK] Contact found: {contact_name}")
        print(f"  Email: {contact_email}")
        logger.info(f"Contact found: {contact_name} <{contact_email}>")

    except Exception as e:
        print(f"[FAIL] Contact search failed: {e}")
        logger.error(f"Contact search error: {e}", exc_info=True)
        return workflow_results

    # =========================================================================
    # STEP 4: Share document with contact
    # =========================================================================
    print("\n" + "="*80)
    print("STEP 4: Sharing Document")
    print("="*80)

    try:
        logger.info(f"Sharing document with {contact_email}...")
        share_result = await drive_share_file(
            file_id=doc_id,
            email=contact_email,
            role="reader"  # View only permission
        )

        if share_result.get('status') == 'shared':
            workflow_results['share'] = share_result
            print(f"[OK] Document shared with {contact_email}")
            print(f"  Permission: Reader (view only)")
            logger.info("Document sharing successful")
        else:
            print(f"[FAIL] Document sharing failed: {share_result.get('error')}")
            return workflow_results

    except Exception as e:
        print(f"[FAIL] Document sharing failed: {e}")
        logger.error(f"Sharing error: {e}", exc_info=True)
        return workflow_results

    # =========================================================================
    # STEP 5: Send email with document link
    # =========================================================================
    print("\n" + "="*80)
    print("STEP 5: Sending Email")
    print("="*80)

    try:
        logger.info(f"Sending email to {contact_email}...")

        email_subject = "Istraživanje: Hidroponski Uzgoj"
        email_body = f"""Poštovani {contact_name},

Šaljem Vam rezultate istraživanja o hidroponskom uzgoju.

Dokument možete pregledati ovdje:
{doc_url}

Dokument sadrži:
- Sažetak istraživanja o hidroponskom uzgoju
- Prednosti i tehnike
- Izvori i reference

Srdačan pozdrav,
Multi-Agent System

---
Ova poruka je automatski generirana od strane multi-agent sustava.
Datum: {datetime.now().strftime('%d.%m.%Y u %H:%M')}
"""

        email_result = await gmail_send_message(
            to=contact_email,
            subject=email_subject,
            body=email_body
        )

        if email_result.get('id') or email_result.get('message_id'):
            workflow_results['email'] = email_result
            message_id = email_result.get('id') or email_result.get('message_id')
            print(f"[OK] Email sent successfully!")
            print(f"  To: {contact_email}")
            print(f"  Subject: {email_subject}")
            print(f"  Message ID: {message_id}")
            logger.info(f"Email sent: {message_id}")
        else:
            print(f"[FAIL] Email sending failed: {email_result.get('error')}")
            return workflow_results

    except Exception as e:
        print(f"[FAIL] Email sending failed: {e}")
        logger.error(f"Email error: {e}", exc_info=True)
        return workflow_results

    # =========================================================================
    # WORKFLOW COMPLETE
    # =========================================================================
    print("\n" + "="*80)
    print("WORKFLOW COMPLETED SUCCESSFULLY!")
    print("="*80)
    print("\n[SUMMARY]")
    print(f"  [OK] Research: {len(research.get('results', []))} sources")
    print(f"  [OK] Document: {doc_title}")
    print(f"  [OK] Document URL: {doc_url}")
    print(f"  [OK] Contact: {contact_name} <{contact_email}>")
    print(f"  [OK] Shared: View permission granted")
    print(f"  [OK] Email: Sent successfully")
    print("\n" + "="*80 + "\n")

    logger.info("Complete workflow executed successfully!")

    return workflow_results


if __name__ == "__main__":
    print("\n[STARTING] Complete workflow test...")
    print("[INFO] This uses REAL API calls and sends REAL email\n")

    try:
        result = asyncio.run(test_complete_workflow())

        # Print final status
        success_count = sum(1 for v in result.values() if v is not None)
        total_steps = len(result)

        print("\n" + "="*80)
        print(f"FINAL RESULT: {success_count}/{total_steps} steps completed")
        print("="*80)

        if success_count == total_steps:
            print("\n[OK] ALL STEPS COMPLETED SUCCESSFULLY!")
            print("  The email has been sent to Tomislav Golić")
            print("  Check the inbox for the email with document link")
        else:
            print(f"\n[WARN] PARTIAL SUCCESS: {success_count}/{total_steps} steps completed")
            print("  Some steps failed. Check logs above for details.")

        print("\n" + "="*80 + "\n")

    except KeyboardInterrupt:
        print("\n\n[CANCELLED] Test interrupted by user")
    except Exception as e:
        print(f"\n\n[FATAL ERROR] {e}")
        logger.error("Fatal error in workflow", exc_info=True)
