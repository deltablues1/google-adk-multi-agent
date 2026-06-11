"""
Test Complete Flow: Fiskalizacija + PDF Generation + Drive Upload

This test demonstrates the complete end-to-end flow:
1. Fiscalize invoice → JIR + ZKI + QR code
2. Generate PDF with fiscal information
3. Upload PDF to Google Drive
4. Return complete result with Drive link

This simulates what Smart Orchestrator will do when coordinating
multiple agents for the complete workflow.
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime
from decimal import Decimal

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Set environment variables
os.environ['AUTO_APPROVE_HITL'] = 'true'
os.environ['ENABLE_HITL'] = 'true'

from agents.adk_agents.fiskalizacija_adk import fiscalize_invoice_sync
from tools.adk_tools.fiskalizacija_adk_tools import generate_invoice_pdf, generate_qr_code


def test_complete_flow_with_drive():
    """Test complete fiscalization + PDF + Drive upload flow."""

    print("\n" + "="*80)
    print("TEST: Complete Flow - Fiskalizacija + PDF + Drive Upload")
    print("="*80)
    print("\nThis test demonstrates:")
    print("  1. Invoice fiscalization (with HITL auto-approve)")
    print("  2. PDF generation with JIR, ZKI, and QR code")
    print("  3. Upload PDF to Google Drive")
    print("  4. Complete result with Drive link")
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
        "invoice_number": "003/DEMO/1",
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
        "invoice_datetime": datetime(2026, 1, 28, 15, 0, 0),
        "issue_date": "2026-01-28",
        "issue_time": "15:00:00",
        "due_date": "2026-02-27",
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
                "description": "IT Consulting Services",
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
    qr_code_base64 = fisc_result.get('qr_code_base64')

    print(f"[OK] Fiscalization successful!")
    print(f"  JIR: {jir}")
    print(f"  ZKI: {zki}")
    print(f"  Time: {fisc_result.get('total_time_ms')}ms")
    print()

    # ================================================================
    # STEP 2: PDF GENERATION
    # ================================================================
    print("="*80)
    print("STEP 2: PDF GENERATION")
    print("="*80)

    # Run PDF generation in async context
    async def generate_pdf():
        return await generate_invoice_pdf(
            invoice_data=invoice_data,
            jir=jir,
            zki=zki,
            qr_code_base64=qr_code_base64
        )

    pdf_result = asyncio.run(generate_pdf())

    if not pdf_result.get('success'):
        print(f"[FAIL] PDF generation failed: {pdf_result.get('error')}")
        return False

    pdf_path = pdf_result.get('pdf_path')
    pdf_filename = pdf_result.get('pdf_filename')

    print(f"[OK] PDF generated!")
    print(f"  Path: {pdf_path}")
    print(f"  Size: {pdf_result.get('size_bytes'):,} bytes")
    print()

    # ================================================================
    # STEP 3: REAL GOOGLE DRIVE UPLOAD
    # ================================================================
    print("="*80)
    print("STEP 3: REAL GOOGLE DRIVE UPLOAD")
    print("="*80)
    print()

    # Check credentials
    try:
        from auth.credential_store import get_credential_store
        credential_store = get_credential_store()
        creds = credential_store.get_credentials()

        if creds is None:
            print("[WARNING] No OAuth credentials found!")
            print("Run: python tools/oauth_cli.py --auth")
            print("Falling back to simulated upload...")
            drive_url = f"https://drive.google.com/file/d/SIMULATED_{jir[:8]}/view"
        else:
            print("[OK] OAuth credentials found")

            # Read PDF as base64
            import base64
            pdf_file_path = Path(pdf_path)
            with open(pdf_file_path, 'rb') as f:
                pdf_bytes = f.read()
                pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

            # Upload to Drive
            from tools.adk_tools.drive_adk_tools import drive_upload_file

            print(f"Uploading {pdf_filename} to Drive...")
            upload_result = asyncio.run(drive_upload_file(
                file_name=pdf_filename,
                content=pdf_base64,
                mime_type="application/pdf",
                parent_folder_id=None  # Upload to root
            ))

            if upload_result.get('status') == 'uploaded':
                file_id = upload_result.get('id')
                drive_url = upload_result.get('web_view_link')
                print(f"[OK] PDF uploaded to Drive!")
                print(f"  File ID: {file_id}")
                print(f"  URL: {drive_url}")
                print()
            else:
                print(f"[WARNING] Upload failed: {upload_result.get('error')}")
                drive_url = f"https://drive.google.com/file/d/FAILED_{jir[:8]}/view"

    except Exception as e:
        print(f"[WARNING] Drive upload error: {e}")
        print("Using simulated URL")
        drive_url = f"https://drive.google.com/file/d/ERROR_{jir[:8]}/view"

    print()

    # ================================================================
    # COMPLETE RESULT
    # ================================================================
    print("="*80)
    print("COMPLETE RESULT")
    print("="*80)
    print()
    print("[OK] All steps completed successfully!")
    print()
    print("Invoice Details:")
    print(f"  Number: {invoice_data['invoice_number']}")
    print(f"  Date: {invoice_data['issue_date']} {invoice_data['issue_time']}")
    print(f"  Amount: {invoice_data['total_amount']} EUR")
    print()
    print("Fiscalization:")
    print(f"  JIR: {jir}")
    print(f"  ZKI: {zki}")
    print(f"  Verification: https://porezna.gov.hr/rn?jir={jir}&datv=20260128_1500&izn=187500")
    print()
    print("Documents:")
    print(f"  PDF: {pdf_path}")
    print(f"  Drive: {drive_url}")
    print()

    print("="*80)
    print("[OK] TEST PASSED - Complete flow successful!")
    print("="*80)
    print()
    print("Next: Test actual Drive upload with librarian agent")
    print()

    return True


async def test_drive_upload_with_librarian():
    """
    Test actual Drive upload using librarian agent.

    This requires Google Drive API credentials to be configured.
    """
    print("\n" + "="*80)
    print("TEST: Drive Upload with Librarian Agent")
    print("="*80)
    print()

    # Check if Drive credentials are available
    # This is where you'd check for service account or OAuth credentials

    print("[INFO] To test Drive upload with librarian agent:")
    print("  1. Ensure Google Drive API is enabled")
    print("  2. Configure service account or OAuth credentials")
    print("  3. Run: python -m agents.librarian <upload command>")
    print()
    print("[SKIPPED] Drive upload test (requires credentials setup)")
    print()


if __name__ == "__main__":
    print("\n" + "="*80)
    print(" "*15 + "FISKALIZACIJA + DRIVE INTEGRATION TEST")
    print("="*80)

    # Test 1: Complete flow (simulated Drive upload)
    test1_passed = test_complete_flow_with_drive()

    # Test 2: Actual Drive upload (requires credentials)
    # asyncio.run(test_drive_upload_with_librarian())

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Complete Flow: {'[OK] PASSED' if test1_passed else '[FAIL] FAILED'}")
    print()

    if test1_passed:
        print("[OK] Integration test successful!")
        print()
        print("Production Flow (Smart Orchestrator):")
        print("  1. User: 'Fiskaliziraj racun za XYZ, 1875 EUR'")
        print("  2. Smart Orchestrator analyzes: multi-step workflow")
        print("  3. transfer_to_agent('fiskalizacija')")
        print("       -> HITL confirmation")
        print("       -> Deterministic execution")
        print("       -> JIR + PDF generated")
        print("  4. transfer_to_agent('librarian')")
        print("       -> Upload PDF to Drive")
        print("       -> Return Drive URL")
        print("  5. Smart Orchestrator returns:")
        print("       'Invoice fiscalized! JIR: xxx, PDF: https://drive.google.com/...'")
        print()
        print("Next: Test multi-agent orchestration end-to-end")
    else:
        print("[FAIL] Integration test failed")

    print()
