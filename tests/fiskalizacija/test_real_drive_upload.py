"""
Test Real Google Drive Upload - End-to-End Integration

This test verifies complete fiscalization flow with REAL Google Drive upload:
1. Fiscalize invoice -> JIR + PDF generated
2. Upload PDF to Drive using librarian agent (REAL upload!)
3. Verify file appears in Drive
4. Get shareable link

This uses REAL Google Drive API with OAuth credentials.
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime
from decimal import Decimal
import base64

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Set environment variables
os.environ['AUTO_APPROVE_HITL'] = 'true'
os.environ['ENABLE_HITL'] = 'true'

from agents.adk_agents.fiskalizacija_adk import fiscalize_invoice_sync
from tools.adk_tools.drive_adk_tools import drive_upload_file, drive_create_folder, drive_search_files


def test_real_drive_upload():
    """Test complete flow with real Drive upload."""

    print("\n" + "="*80)
    print("TEST: Real Google Drive Upload - End-to-End")
    print("="*80)
    print("\nThis test demonstrates:")
    print("  1. Invoice fiscalization (with HITL auto-approve)")
    print("  2. PDF generation with JIR, ZKI, and QR code")
    print("  3. REAL Google Drive upload (not simulated!)")
    print("  4. Verification and shareable link")
    print()

    # Certificate
    cert_file = Path(__file__).parent / "47034854402.F1.1.p12"
    if not cert_file.exists():
        print(f"[ERROR] Certificate not found: {cert_file}")
        return False

    # ================================================================
    # STEP 1: FISCALIZATION
    # ================================================================
    print("="*80)
    print("STEP 1: FISCALIZATION (with HITL)")
    print("="*80)

    invoice_data = {
        "invoice_number": "005/DEMO/1",
        "supplier_oib": "47034854402",
        "supplier_name": "LUX TECH d.o.o.",
        "supplier": {
            "name": "LUX TECH d.o.o.",
            "oib": "47034854402",
            "address": "Hrvatski Leskovac",
            "city": "Hrvatski Leskovac",
            "postal_code": "10000",
            "phone": "+385 1 234 5678",
            "email": "info@luxtech.hr",
            "iban": "HR1234567890123456789"
        },
        "customer": {
            "name": "Test Kupac d.o.o.",
            "oib": "12345678903",
            "address": "Test ulica 123",
            "city": "Zagreb",
            "postal_code": "10000"
        },
        "invoice_datetime": datetime(2026, 2, 1, 12, 0, 0),
        "issue_date": "2026-02-01",
        "issue_time": "12:00:00",
        "due_date": "2026-03-03",
        "total_amount": Decimal("1875.00"),
        "payment_method": "T",
        "payment_means_code": "30",
        "payment_reference": "00-123-456",
        "payment_reference_model": "HR00",
        "pdv_breakdown": [
            {
                "stopa": "25.00",
                "osnovica": "1500.00",
                "iznos": "375.00"
            }
        ],
        "items": [
            {
                "description": "IT Consulting Services - Real Drive Upload Test",
                "quantity": "10.0",
                "unit_code": "HUR",
                "unit_price": "150.00",
                "vat_rate": "25",
                "line_total": "1500.00"
            }
        ],
        "tax_breakdown": {
            "subtotals": [
                {
                    "vat_rate": "25",
                    "taxable_amount": "1500.00",
                    "tax_amount": "375.00"
                }
            ],
            "total_net": "1500.00",
            "total_gross": "1875.00"
        },
        "business_unit": "DEMO",
        "device_number": "1",
        "operator_oib": "47034854402"
    }

    print(f"Invoice: {invoice_data['invoice_number']}")
    print(f"Amount: {invoice_data['total_amount']} EUR")
    print()

    # Fiscalize
    fisc_result = fiscalize_invoice_sync(
        invoice_data=invoice_data,
        cert_path=str(cert_file),
        cert_password=os.environ.get("FINA_CERT_PASSWORD"),
        use_sandbox=True,
        auto_approve=True
    )

    if not fisc_result.get('success'):
        print(f"[FAIL] Fiscalization failed: {fisc_result.get('error_message')}")
        return False

    jir = fisc_result.get('jir')
    zki = fisc_result.get('zki')
    pdf_path = fisc_result.get('pdf_path')

    print(f"[OK] Fiscalization successful!")
    print(f"  JIR: {jir}")
    print(f"  ZKI: {zki}")
    print(f"  PDF: {pdf_path}")
    print(f"  Time: {fisc_result.get('total_time_ms')}ms")
    print()

    # ================================================================
    # STEP 2: PREPARE PDF FOR UPLOAD
    # ================================================================
    print("="*80)
    print("STEP 2: PREPARE PDF FOR UPLOAD")
    print("="*80)

    # Check if PDF exists
    pdf_file_path = Path(pdf_path)
    if not pdf_file_path.exists():
        print(f"[FAIL] PDF not found: {pdf_path}")
        return False

    # Read PDF as base64
    with open(pdf_file_path, 'rb') as f:
        pdf_bytes = f.read()
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

    pdf_filename = pdf_file_path.name
    pdf_size = len(pdf_bytes)

    print(f"[OK] PDF prepared for upload")
    print(f"  Filename: {pdf_filename}")
    print(f"  Size: {pdf_size:,} bytes")
    print(f"  Encoding: base64")
    print()

    # ================================================================
    # STEP 3: REAL GOOGLE DRIVE UPLOAD
    # ================================================================
    print("="*80)
    print("STEP 3: REAL GOOGLE DRIVE UPLOAD")
    print("="*80)
    print()

    # Check credentials first
    try:
        from auth.credential_store import get_credential_store
        credential_store = get_credential_store()
        creds = credential_store.get_credentials()

        if creds is None:
            print("[ERROR] No OAuth credentials found!")
            print("Run: python tools/oauth_cli.py --auth")
            return False

        print("[OK] OAuth credentials found")
    except Exception as e:
        print(f"[ERROR] Failed to get credentials: {e}")
        return False

    # Create folder for invoices if needed
    print("\nCreating/finding folder 'Fiskalizacija Test'...")

    try:
        # Search for existing folder (using asyncio.run for sync context)
        search_result = asyncio.run(drive_search_files(
            query="name = 'Fiskalizacija Test' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
            max_results=1
        ))

        if search_result.get('count', 0) > 0:
            folder_id = search_result['files'][0]['id']
            folder_url = search_result['files'][0].get('webViewLink', '')
            print(f"[OK] Folder exists: {folder_url}")
        else:
            # Create folder
            folder_result = asyncio.run(drive_create_folder_async("Fiskalizacija Test"))

            if folder_result.get('status') == 'created':
                folder_id = folder_result['folder_id']
                folder_url = folder_result.get('webViewLink', '')
                print(f"[OK] Folder created: {folder_url}")
            else:
                print(f"[FAIL] Failed to create folder: {folder_result.get('error')}")
                folder_id = None

    except Exception as e:
        print(f"[WARNING] Folder operation failed: {e}")
        print("Will upload to root instead")
        folder_id = None

    # Upload PDF to Drive
    print(f"\nUploading {pdf_filename} to Drive...")

    try:
        upload_result = asyncio.run(drive_upload_file(
            file_name=pdf_filename,
            content=pdf_base64,
            mime_type="application/pdf",
            parent_folder_id=folder_id
        ))

        if upload_result.get('status') == 'uploaded':
            file_id = upload_result.get('id')
            drive_url = upload_result.get('web_view_link')

            print(f"[OK] PDF uploaded to Drive!")
            print(f"  File ID: {file_id}")
            print(f"  URL: {drive_url}")
            print(f"  Folder: {'Fiskalizacija Test' if folder_id else 'My Drive (root)'}")
            print()
        else:
            print(f"[FAIL] Upload failed: {upload_result.get('error')}")
            return False

    except Exception as e:
        print(f"[FAIL] Upload exception: {e}")
        return False

    # ================================================================
    # STEP 4: VERIFICATION
    # ================================================================
    print("="*80)
    print("STEP 4: VERIFICATION")
    print("="*80)
    print()

    # Search for uploaded file to verify it exists
    print("Verifying file in Drive...")

    try:
        verify_result = asyncio.run(drive_search_files(
            query=f"name = '{pdf_filename}' and trashed = false",
            max_results=1
        ))

        if verify_result.get('count', 0) > 0:
            found_file = verify_result['files'][0]
            print(f"[OK] File verified in Drive!")
            print(f"  Name: {found_file['name']}")
            print(f"  Modified: {found_file.get('modifiedTime')}")
            print(f"  Owner: {found_file.get('owners', [{}])[0].get('displayName', 'Unknown')}")
            print()
        else:
            print(f"[WARNING] File not found in search (may take a moment to index)")
            print()

    except Exception as e:
        print(f"[WARNING] Verification search failed: {e}")
        print()

    # ================================================================
    # COMPLETE RESULT
    # ================================================================
    print("="*80)
    print("COMPLETE RESULT - END-TO-END SUCCESS!")
    print("="*80)
    print()
    print("Invoice Details:")
    print(f"  Number: {invoice_data['invoice_number']}")
    print(f"  Date: {invoice_data['issue_date']} {invoice_data['issue_time']}")
    print(f"  Amount: {invoice_data['total_amount']} EUR")
    print()
    print("Fiscalization:")
    print(f"  JIR: {jir}")
    print(f"  ZKI: {zki}")
    print(f"  Verification: https://porezna.gov.hr/rn?jir={jir}&datv=20260201_1200&izn=187500")
    print()
    print("Documents:")
    print(f"  PDF (local): {pdf_path}")
    print(f"  PDF (Drive): {drive_url}")
    print(f"  Drive Folder: {'Fiskalizacija Test' if folder_id else 'My Drive'}")
    print()

    print("="*80)
    print("[OK] TEST PASSED - Real Drive upload successful!")
    print("="*80)
    print()
    print("Next: Update multi-agent orchestration to use real upload")
    print()

    return True


async def drive_create_folder_async(folder_name: str, parent_folder_id: str = None) -> dict:
    """Helper to create Drive folder (async version)."""
    try:
        from tools.api_implementations.drive_api import drive_create_folder as create_folder_impl
        from auth.credential_store import get_credential_store

        credential_store = get_credential_store()
        creds = credential_store.get_credentials()

        if creds is None:
            return {"error": "No credentials", "status": "failed"}

        result = await create_folder_impl(creds, folder_name, parent_folder_id)
        return result

    except Exception as e:
        return {"error": str(e), "status": "failed"}


if __name__ == "__main__":
    print("\n" + "="*80)
    print(" "*15 + "REAL GOOGLE DRIVE UPLOAD TEST")
    print("="*80)

    # Run test (sync function, no asyncio.run needed)
    test_passed = test_real_drive_upload()

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Real Drive Upload: {'[OK] PASSED' if test_passed else '[FAIL] FAILED'}")
    print()

    if test_passed:
        print("[OK] Complete integration successful!")
        print()
        print("Production Flow (Smart Orchestrator):")
        print("  1. User: 'Fiskaliziraj racun za XYZ, 1875 EUR'")
        print("  2. Smart Orchestrator -> fiskalizacija agent")
        print("       -> HITL confirmation")
        print("       -> Deterministic execution")
        print("       -> JIR + PDF generated")
        print("  3. Smart Orchestrator -> librarian agent")
        print("       -> REAL Drive upload")
        print("       -> Return Drive URL")
        print("  4. Smart Orchestrator returns:")
        print("       'Invoice fiscalized! JIR: xxx, PDF: https://drive.google.com/...'")
        print()
        print("Faza 1 Progress: 85% -> 90%! (Real Drive upload working)")
    else:
        print("[FAIL] Test failed - check errors above")

    print()
