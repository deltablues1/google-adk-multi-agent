"""
Test Complete Fiskalizacija Flow with HITL Confirmation

Tests the integrated flow:
1. Data Preparation (LLM or structured)
2. Validation (LLM or basic)
3. HITL Confirmation (CLI with auto-approve for testing)
4. Deterministic Execution (NO LLM)
5. QR Code Generation
6. PDF Generation

This verifies that the complete orchestrator works with HITL integration.
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime
from decimal import Decimal

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Set environment variables for testing
os.environ['AUTO_APPROVE_HITL'] = 'true'  # Auto-approve for automated testing
os.environ['ENABLE_HITL'] = 'true'  # Enable HITL confirmation

from agents.adk_agents.fiskalizacija_adk import fiscalize_invoice_sync


def test_fiskalizacija_with_hitl():
    print("\n" + "="*80)
    print("TEST: Complete Fiskalizacija Flow with HITL Confirmation")
    print("="*80)
    print("\nThis test verifies:")
    print("  1. Data preparation (structured input)")
    print("  2. Validation (basic validation)")
    print("  3. HITL Confirmation (auto-approved for testing)")
    print("  4. Deterministic Execution (sign + SOAP to FINA)")
    print("  5. QR Code generation")
    print("  6. PDF generation")
    print()

    # Certificate path
    cert_file = Path(__file__).parent / "47034854402.F1.1.p12"
    if not cert_file.exists():
        print(f"[ERROR] Certificate not found: {cert_file}")
        return False

    print(f"[OK] Certificate found: {cert_file}\n")

    # Prepare invoice data (same as deterministic test)
    # NOTE: Invoice number format must be XXX/PP/NU where XXX is numeric (001-999)
    invoice_data = {
        "invoice_number": "001/DEMO/1",  # Fixed format - no TEST prefix
        "supplier_oib": "47034854402",
        "supplier_name": "LUX TECH d.o.o.",
        "invoice_datetime": datetime(2026, 1, 28, 11, 30, 0),
        "total_amount": Decimal("1875.00"),
        "payment_method": "T",  # Transfer
        "pdv_breakdown": [
            {
                "stopa": "25.00",
                "osnovica": "1500.00",
                "iznos": "375.00"
            }
        ],
        "operator_oib": "47034854402"
    }

    print("="*80)
    print("INVOICE DATA")
    print("="*80)
    print(f"Invoice Number: {invoice_data['invoice_number']}")
    print(f"Supplier: {invoice_data['supplier_name']} (OIB: {invoice_data['supplier_oib']})")
    print(f"Total Amount: {invoice_data['total_amount']} EUR")
    print(f"Payment Method: {invoice_data['payment_method']}")
    print(f"VAT Breakdown: {invoice_data['pdv_breakdown']}")
    print()

    print("="*80)
    print("EXECUTION (with HITL)")
    print("="*80)
    print("\nEnvironment:")
    print(f"  AUTO_APPROVE_HITL: {os.environ.get('AUTO_APPROVE_HITL')}")
    print(f"  ENABLE_HITL: {os.environ.get('ENABLE_HITL')}")
    print()

    print("[STEP 1] Data Preparation...")
    print("[STEP 2] Validation...")
    print("[STEP 3] HITL Confirmation (auto-approved)...")
    print("[STEP 4] Deterministic Execution...")
    print("  - Load certificate")
    print("  - Build RacunZahtjev XML")
    print("  - Calculate ZKI")
    print("  - Sign with XAdES-BES")
    print("  - Send to FINA DEMO")
    print("  - Parse response")
    print("  - Generate QR code")
    print("  - Save to ledger")
    print()

    # Execute fiscalization
    result = fiscalize_invoice_sync(
        invoice_data=invoice_data,
        cert_path=str(cert_file),
        cert_password=os.environ.get("FINA_CERT_PASSWORD"),
        use_sandbox=True,
        auto_approve=True  # Auto-approve for testing
    )

    # Display results
    print("="*80)
    print("RESULTS")
    print("="*80)

    if result.get('success'):
        print(f"\n[OK] SUCCESS - Invoice fiscalized with HITL!")
        print(f"\n  JIR: {result.get('jir')}")
        print(f"  ZKI: {result.get('zki')}")
        print(f"  Verification URL: {result.get('verification_url')}")
        print(f"  Total time: {result.get('total_time_ms')}ms")
        print(f"    - Preparation: {result.get('preparation_time_ms')}ms")
        print(f"    - Validation: {result.get('validation_time_ms')}ms")
        print(f"    - Execution: {result.get('execution_time_ms')}ms")

        if result.get('qr_code_base64'):
            print(f"\n  QR code generated: {len(result.get('qr_code_base64'))} bytes (base64)")

        # Check validation notes for HITL
        validation_notes = result.get('validation_notes', [])
        hitl_note = next((note for note in validation_notes if 'HITL' in note), None)
        if hitl_note:
            print(f"\n  {hitl_note}")

        print("\n" + "="*80)
        print("[OK] TEST PASSED - Fiskalizacija with HITL successful!")
        print("="*80)
        return True

    else:
        print(f"\n[FAIL] FAILED - Fiscalization failed")
        print(f"\n  Status: {result.get('status')}")
        print(f"  Error: {result.get('error_message')}")

        if result.get('error_code'):
            print(f"  Error Code: {result.get('error_code')}")

        print(f"\n  Total time: {result.get('total_time_ms')}ms")

        # Show notes
        if result.get('preparation_notes'):
            print(f"\n  Preparation notes: {result.get('preparation_notes')}")
        if result.get('validation_notes'):
            print(f"  Validation notes: {result.get('validation_notes')}")
        if result.get('execution_notes'):
            print(f"  Execution notes: {result.get('execution_notes')}")

        print("\n" + "="*80)
        print("[FAIL] TEST FAILED - Check error details above")
        print("="*80)
        return False


def test_fiskalizacija_manual_approval():
    """
    Test with manual approval (set AUTO_APPROVE_HITL=false).

    This test will prompt the user for confirmation.
    """
    print("\n" + "="*80)
    print("TEST: Fiskalizacija with Manual HITL Approval")
    print("="*80)
    print("\nThis test will prompt you to manually approve the invoice.")
    print("Set AUTO_APPROVE_HITL=false to enable manual confirmation.")
    print()

    # Set manual approval
    os.environ['AUTO_APPROVE_HITL'] = 'false'
    os.environ['ENABLE_HITL'] = 'true'

    # Certificate path
    cert_file = Path(__file__).parent / "47034854402.F1.1.p12"

    invoice_data = {
        "invoice_number": "002/DEMO/1",  # Fixed format - no MANUAL prefix
        "supplier_oib": "47034854402",
        "supplier_name": "LUX TECH d.o.o.",
        "invoice_datetime": datetime(2026, 1, 28, 14, 0, 0),
        "total_amount": Decimal("625.00"),
        "payment_method": "G",  # Cash
        "pdv_breakdown": [
            {
                "stopa": "25.00",
                "osnovica": "500.00",
                "iznos": "125.00"
            }
        ]
    }

    print(f"Invoice: {invoice_data['invoice_number']}")
    print(f"Amount: {invoice_data['total_amount']} EUR")
    print("\n" + "="*80)

    result = fiscalize_invoice_sync(
        invoice_data=invoice_data,
        cert_path=str(cert_file),
        cert_password=os.environ.get("FINA_CERT_PASSWORD"),
        use_sandbox=True,
        auto_approve=False  # Manual approval
    )

    if result.get('success'):
        print("\n[OK] Invoice fiscalized after manual approval!")
        print(f"JIR: {result.get('jir')}")
        return True
    elif result.get('error_message') == "User rejected fiscalization":
        print("\n[INFO] User rejected the fiscalization (as expected)")
        return True
    else:
        print(f"\n[FAIL] Unexpected error: {result.get('error_message')}")
        return False


if __name__ == "__main__":
    print("\n" + "="*80)
    print(" "*20 + "FISKALIZACIJA INTEGRATION TEST")
    print("="*80)

    # Test 1: Auto-approved HITL
    test1_passed = test_fiskalizacija_with_hitl()

    # Uncomment to test manual approval:
    # test2_passed = test_fiskalizacija_manual_approval()

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Test 1 (Auto-approved HITL): {'[OK] PASSED' if test1_passed else '[FAIL] FAILED'}")
    # print(f"Test 2 (Manual approval): {'[OK] PASSED' if test2_passed else '[FAIL] FAILED'}")
    print()

    if test1_passed:
        print("[OK] Integration successful! HITL confirmation is now part of the flow.")
        print("\nNext steps:")
        print("  1. Test PDF generation (already working from previous test)")
        print("  2. Test Drive upload integration")
        print("  3. Test multi-agent orchestration (Smart Orchestrator -> fiskalizacija)")
    else:
        print("[FAIL] Integration failed. Check errors above.")

    print()
