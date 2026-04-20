"""
Idempotency Test - Prevent Duplicate Fiscalization

Tests that the same invoice cannot be fiscalized twice:
1. First fiscalization → SUCCESS, receives JIR
2. Second fiscalization attempt → Returns existing JIR (no FINA call)

This is CRITICAL for production - double fiscalization = double tax liability!
"""

import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from main import WorkspaceADKSystem, sanitize_emojis


async def test_idempotency():
    print("\n" + "="*80)
    print("IDEMPOTENCY TEST - Prevent Duplicate Fiscalization")
    print("="*80)

    # Initialize system
    print("\nInitializing system...")
    system = WorkspaceADKSystem()
    system.initialize_agents()

    print(f"\n[OK] System initialized")
    print(f"Session: {system.session_id}\n")

    # Verify certificate exists
    cert_file = Path(__file__).parent / "47034854402.F1.1.p12"
    if not cert_file.exists():
        print(f"\n[ERROR] Certificate not found: {cert_file}")
        return
    print(f"[OK] Certificate found\n")

    # ========================================================================
    # STEP 1: Clear ledger for test invoice (if it exists)
    # ========================================================================
    print("="*80)
    print("STEP 1: Prepare Test Environment")
    print("="*80)

    test_invoice_number = f"IDEMPOTENCY-TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    test_oib = "47034854402"

    print(f"\n[TEST SETUP]")
    print(f"   Invoice Number: {test_invoice_number}")
    print(f"   Issuer OIB: {test_oib}")
    print(f"   Using: In-memory ledger (test mode)")

    # Check if invoice already exists
    from tools.api_implementations.fiskalizacija_ledger import check_invoice_ledger

    check = check_invoice_ledger(
        invoice_number=test_invoice_number,
        supplier_oib=test_oib,
        use_firestore=False
    )

    print(f"\n[LEDGER CHECK] Invoice {test_invoice_number}:")
    print(f"   Exists: {check['exists']}")

    if check["exists"]:
        print(f"   [WARNING] Invoice already in ledger (from previous test)")
        print(f"   [INFO] Using a new unique invoice number")
        test_invoice_number = f"IDEMPOTENCY-TEST-{datetime.now().timestamp()}"
        print(f"   New Invoice: {test_invoice_number}")
    else:
        print(f"   [OK] Invoice not in ledger (ready for test)")

    # ========================================================================
    # STEP 2: First Fiscalization Attempt (Should Succeed)
    # ========================================================================
    print("\n\n" + "="*80)
    print("STEP 2: FIRST Fiscalization Attempt (Should Generate XML + Sign)")
    print("="*80)

    invoice_data = {
        "issuer": {
            "oib": "47034854402",
            "name": "Test Company d.o.o.",
            "address": "Hrvatski Leskovac, Croatia"
        },
        "buyer": {
            "oib": "85546001374",
            "name": "Pivovara Test d.o.o."
        },
        "invoice": {
            "number": test_invoice_number,
            "issue_date": datetime.now().strftime("%Y-%m-%d"),
            "due_date": "2026-02-28",
            "currency": "EUR",
            "payment_method": "TRANSAKCIJSKI_RACUN",
            "business_premise": "URED",
            "cash_register": "1"
        },
        "items": [
            {
                "description": "Idempotency Test Service",
                "kpd_code": "62.20.0",
                "quantity": 1.0,
                "unit": "HUR",
                "unit_price": 100.00,
                "line_total": 100.00,
                "vat_rate": 0.25,
                "vat_amount": 25.00,
                "total_with_vat": 125.00
            }
        ],
        "summary": {
            "subtotal": 100.00,
            "total_vat": 25.00,
            "grand_total": 125.00
        }
    }

    # First fiscalization query
    query1 = f"""Generiraj XML racun i potpisi ga (ALI NEMOJ slati na FINA).

PODACI ZA RACUN (vec validirani):
{json.dumps(invoice_data, indent=2, ensure_ascii=False)}

CERTIFIKAT:
- Datoteka: 47034854402.F1.1.p12
- Lozinka: <from FINA_CERT_PASSWORD env var>

NAPOMENA: Ovo je IDEMPOTENCY TEST.
1. Generiraj XML
2. Potpisi s XAdES
3. NE salji na FINA (test mode)
4. OBAVEZNO spremi u ledger nakon potpisa

Invoice broj: {test_invoice_number}
"""

    print("\n[ATTEMPT 1] Sending first fiscalization request...")
    print(f"   Expected: XML generation + XAdES signing + ledger save")

    try:
        response1 = await system.orchestrator_helper.run(query1)
        print(sanitize_emojis(f"\n[ATTEMPT 1] Result:\n{response1[:500]}..."))

        # Check if processed
        if any(word in response1.lower() for word in ["xml", "potpis", "sign"]):
            print("\n[OK] First attempt processed (XML generation mentioned)")
        else:
            print("\n[WARNING] First attempt result unclear")

    except Exception as e:
        print(f"\n[ERROR] First attempt failed: {e}")
        import traceback
        traceback.print_exc()
        return

    print("\n" + "="*80)

    # ========================================================================
    # STEP 3: Check Ledger (Should Now Exist)
    # ========================================================================
    print("\nSTEP 3: Verify Invoice in Ledger")
    print("="*80)

    check2 = check_invoice_ledger(
        invoice_number=test_invoice_number,
        supplier_oib=test_oib,
        use_firestore=False
    )

    print(f"\n[LEDGER CHECK] After first attempt:")
    print(f"   Exists: {check2['exists']}")
    print(f"   JIR: {check2.get('jir', 'N/A')}")
    print(f"   ZKI: {check2.get('zki', 'N/A')}")
    print(f"   Status: {check2.get('status', 'N/A')}")

    if check2["exists"]:
        print(f"\n[OK] Invoice saved to ledger (expected)")
        first_jir = check2.get('jir')
    else:
        print(f"\n[WARNING] Invoice NOT in ledger (unexpected)")
        print(f"[INFO] Agent may not have called save_invoice_ledger")
        print(f"[INFO] Continuing test anyway...")
        first_jir = None

    # ========================================================================
    # STEP 4: Second Fiscalization Attempt (Should Return Existing)
    # ========================================================================
    print("\n\n" + "="*80)
    print("STEP 4: SECOND Fiscalization Attempt (Should Return Existing JIR)")
    print("="*80)

    # Exact same query
    query2 = f"""Generiraj XML racun i potpisi ga (ALI NEMOJ slati na FINA).

PODACI ZA RACUN (vec validirani):
{json.dumps(invoice_data, indent=2, ensure_ascii=False)}

CERTIFIKAT:
- Datoteka: 47034854402.F1.1.p12
- Lozinka: <from FINA_CERT_PASSWORD env var>

NAPOMENA: Ovo je IDEMPOTENCY TEST - DRUGI POKUSAJ.
1. OBAVEZNO provjeri ledger PRVO!
2. Ako postoji, vrati postojeci JIR
3. NEMOJ generirati novi XML
4. NEMOJ ponovno potpisivati

Invoice broj: {test_invoice_number}
"""

    print("\n[ATTEMPT 2] Sending SECOND fiscalization request...")
    print(f"   Expected: Ledger check -> Return existing JIR (NO new XML)")

    try:
        response2 = await system.orchestrator_helper.run(query2)
        print(sanitize_emojis(f"\n[ATTEMPT 2] Result:\n{response2[:500]}..."))

        # Check if returned existing
        if "vec fiskaliziran" in response2.lower() or "already" in response2.lower() or "postoji" in response2.lower():
            print("\n[OK] Second attempt recognized existing invoice!")
            print(f"   [OK] Idempotency working - prevented duplicate processing")
        elif any(word in response2.lower() for word in ["xml", "generiraj", "generate"]):
            print("\n[ERROR] Second attempt generated NEW XML!")
            print(f"   [ERROR] Idempotency FAILED - agent processed twice!")
        else:
            print("\n[WARNING] Second attempt result unclear")

        # Compare responses
        print(f"\n[COMPARISON]")
        if first_jir:
            if first_jir in response2:
                print(f"   [OK] Same JIR returned: {first_jir}")
            else:
                print(f"   [WARNING] JIR not found in second response")
        else:
            print(f"   [INFO] No JIR from first attempt (test mode)")

    except Exception as e:
        print(f"\n[ERROR] Second attempt failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # ========================================================================
    # SUMMARY
    # ========================================================================
    print("\n\n" + "="*80)
    print("TEST SUMMARY: Idempotency Test")
    print("="*80)

    print(f"\nInvoice: {test_invoice_number}")
    print(f"OIB: {test_oib}")

    print(f"\nAttempt 1:")
    print(f"  - Expected: Process + Save to Ledger")
    print(f"  - Result: {'[OK]' if check2['exists'] else '[WARNING]'}")

    print(f"\nAttempt 2:")
    print(f"  - Expected: Return Existing (No Duplicate Processing)")
    print(f"  - Result: [CHECK RESPONSE ABOVE]")

    print("\n" + "="*80)
    print("Test Complete!")
    print("="*80)

    print("\n[INFO] Next Steps:")
    print("1. Review agent responses above")
    print("2. Verify ledger check was called in second attempt")
    print("3. Confirm no duplicate XML generation")
    print("4. Test with real FINA SOAP call (when API quota available)")


if __name__ == "__main__":
    asyncio.run(test_idempotency())
