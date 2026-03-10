"""
Test Deterministicke Fiskalizacije - BEZ LLM AGENTA

Testira stvarni sustav koji je implementiran za produkciju.
Zaobilazi AI agente i koristi čisti Python kod.

Pipeline:
1. Build XML (fina_xml_builder.py)
2. Calculate ZKI (xades_signer.py)
3. Sign with XAdES (xades_signer.py)
4. Send to FINA (fina_soap_client.py)
5. Parse response
6. Generate QR code
7. Save to ledger
8. Generate PDF

Ovaj test provjerava da li je s006 greška riješena s dodanim metadatama.
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from tools.api_implementations.deterministic_executor import (
    DeterministicFiscalExecutor,
    ExecutorInput,
)


async def test_deterministic_fiscalization():
    print("\n" + "="*80)
    print("TEST: Deterministička Fiskalizacija (BEZ AI AGENATA)")
    print("="*80)
    print("\nOvaj test koristi čisti Python kod bez LLM poziva.")
    print("Testira da li je s006 greška riješena s dodanim metadatama.\n")

    # Certificate path
    cert_file = Path(__file__).parent / "47034854402.F1.1.p12"
    if not cert_file.exists():
        print(f"[ERROR] Certificate not found: {cert_file}")
        return

    print(f"[OK] Certificate found: {cert_file}\n")

    # Prepare invoice data
    invoice_data = ExecutorInput(
        # Invoice identification
        invoice_number="001/DEMO/1",
        supplier_oib="47034854402",

        # Certificate
        cert_path=str(cert_file),
        cert_password="NinuPiL1903",

        # Invoice datetime
        invoice_datetime=datetime(2026, 1, 28, 11, 30, 0),

        # Amounts
        total_amount=Decimal("1875.00"),

        # Payment method
        payment_method="T",  # Transfer (TRANSAKCIJSKI_RACUN)

        # VAT breakdown
        pdv_breakdown=[
            {
                "stopa": "25.00",
                "osnovica": "1500.00",
                "iznos": "375.00"
            }
        ],

        # Operator
        operator_oib="47034854402",

        # Options
        is_late_delivery=False,
        use_sandbox=True
    )

    print("="*80)
    print("INVOICE DATA")
    print("="*80)
    print(f"Invoice Number: {invoice_data.invoice_number}")
    print(f"Supplier OIB: {invoice_data.supplier_oib}")
    print(f"Total Amount: {invoice_data.total_amount} EUR")
    print(f"Payment Method: {invoice_data.payment_method}")
    print(f"Invoice DateTime: {invoice_data.invoice_datetime}")
    print(f"VAT Breakdown: {invoice_data.pdv_breakdown}")
    print(f"Sandbox: {invoice_data.use_sandbox}")
    print()

    # Create executor
    print("="*80)
    print("EXECUTION")
    print("="*80)

    executor = DeterministicFiscalExecutor(
        use_ledger=True,
        use_firestore=False  # Use in-memory ledger for testing
    )

    print("\n[STEP 1] Idempotency check...")
    print("[STEP 2] Load certificate...")
    print("[STEP 3] Calculate ZKI...")
    print("[STEP 4] Build FINA RacunZahtjev XML...")
    print("[STEP 5] Sign XML with XAdES-BES...")
    print("[STEP 6] Send to FINA DEMO via SOAP...")
    print("[STEP 7] Parse FINA response...")
    print("[STEP 8] Generate QR code...")
    print("[STEP 9] Save to ledger...")
    print()

    # Execute
    result = executor.execute(invoice_data)

    # Display results
    print("="*80)
    print("RESULTS")
    print("="*80)

    if result.success:
        print(f"\n[OK] SUCCESS - Invoice fiscalized!")
        print(f"\n  JIR: {result.jir}")
        print(f"  ZKI: {result.zki}")
        print(f"  Verification URL: {result.verification_url}")
        print(f"  Execution time: {result.execution_time_ms}ms")

        if result.qr_code_base64:
            print(f"\n  QR code generated: {len(result.qr_code_base64)} bytes (base64)")

        print("\n" + "="*80)
        print("[OK] TEST PASSED - Fiskalizacija uspjesna!")
        print("="*80)

    else:
        print(f"\n[FAIL] FAILED - Fiscalization failed")
        print(f"\n  Error Code: {result.error_code}")
        print(f"  Error Message: {result.error_message}")
        print(f"  Error Type: {result.error_type}")
        print(f"  HTTP Status: {result.http_status}")
        print(f"  Execution time: {result.execution_time_ms}ms")

        if result.error_type == "transient":
            print("\n  [WARN]  This is a TRANSIENT error - invoice added to retry queue")
            print("      The system will automatically retry within 48 hours")
        else:
            print("\n  [FAIL] This is a PERMANENT error - fix required before retry")

        # Show FINA response for debugging
        if result.fina_response:
            print("\n" + "-"*80)
            print("FINA RESPONSE (for debugging):")
            print("-"*80)
            print(result.fina_response[:1000])  # First 1000 chars
            if len(result.fina_response) > 1000:
                print(f"... (truncated, total {len(result.fina_response)} chars)")

        print("\n" + "="*80)
        print("[FAIL] TEST FAILED - Check error details above")
        print("="*80)

    # Additional info
    print("\n" + "="*80)
    print("NEXT STEPS")
    print("="*80)

    if result.success:
        print("\n1. [OK] JIR received from FINA")
        print("2. [OK] Invoice saved to ledger")
        print("3. Generate PDF invoice with JIR and QR code")
        print("4. Upload documents to Google Drive")
    else:
        if result.error_code == "s006":
            print("\n[WARN]  s006 error detected - 'Sistemska pogreška'")
            print("\nPossible causes:")
            print("  1. Missing metadata in XML (should be fixed in our implementation)")
            print("  2. FINA DEMO environment instability")
            print("  3. Certificate/signing issue")
            print("\nDebugging steps:")
            print("  1. Check generated XML structure")
            print("  2. Verify all required fields are present")
            print("  3. Try again (DEMO can be unstable)")
            print("  4. Contact FINA support if persists")
        elif result.error_type == "transient":
            print("\n1. Invoice added to retry queue")
            print("2. System will retry automatically")
            print("3. Check retry queue status in Firestore")
        else:
            print("\n1. Fix the error in invoice data")
            print("2. Re-run fiscalization after fix")

    print()


if __name__ == "__main__":
    asyncio.run(test_deterministic_fiscalization())
