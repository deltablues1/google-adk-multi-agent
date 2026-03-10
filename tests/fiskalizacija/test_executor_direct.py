"""
Direct Fiskalni Executor Test

Tests XML generation and XAdES signing by calling Executor agent directly
with pre-prepared invoice data, bypassing Pripremac/Validator pipeline.

This tests the EXECUTION layer only (XML + signature generation).
"""

import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from main import WorkspaceADKSystem, sanitize_emojis


async def test_executor_direct():
    print("\n" + "="*80)
    print("DIRECT FISKALNI EXECUTOR TEST")
    print("Tests: XML Generation + XAdES Signing (bypassing validation)")
    print("="*80)

    # Initialize system
    print("\nInitializing system...")
    system = WorkspaceADKSystem()
    system.initialize_agents()

    print(f"\n[OK] System initialized")
    print(f"Session: {system.session_id}")

    # Verify certificate exists
    cert_file = Path(__file__).parent / "47034854402.F1.1.p12"
    if not cert_file.exists():
        print(f"\n[ERROR] Certificate not found: {cert_file}")
        return
    print(f"[OK] Certificate found: {cert_file}\n")

    # ========================================================================
    # TEST 1: Direct Executor Call with Pre-Validated Data
    # ========================================================================
    print("="*80)
    print("TEST 1: Call Executor Directly with Pre-Validated Invoice Data")
    print("="*80)

    # Pre-prepared invoice data (as if it came from Pripremac/Validator)
    invoice_data = {
        "issuer": {
            "oib": "47034854402",
            "name": "Test Company d.o.o.",
            "address": "Testna 1, 10000 Zagreb, Croatia"
        },
        "buyer": {
            "oib": "85546001374",
            "name": "Pivovara Test d.o.o."
        },
        "invoice": {
            "number": "001/URED/1",
            "issue_date": "2026-01-27",
            "due_date": "2026-02-27",
            "currency": "EUR",
            "payment_method": "TRANSAKCIJSKI_RACUN",
            "business_premise": "URED",
            "cash_register": "1"
        },
        "items": [
            {
                "description": "Usluga IT konzultacija",
                "kpd_code": "62.20.0",
                "quantity": 10.0,
                "unit": "HUR",  # UN/ECE code for hour
                "unit_price": 150.00,
                "line_total": 1500.00,
                "vat_rate": 0.25,
                "vat_amount": 375.00,
                "total_with_vat": 1875.00
            }
        ],
        "summary": {
            "subtotal": 1500.00,
            "total_vat": 375.00,
            "grand_total": 1875.00
        }
    }

    # Create the query for Executor
    query = f"""Generiraj XML racun i potpisi ga XAdES potpisom koristeći certifikat 47034854402.F1.1.p12.

Podaci za racun (već validirani):

{json.dumps(invoice_data, indent=2, ensure_ascii=False)}

NAPOMENA: Ovo je DEMO okruženje. Generiraj XML i XAdES potpis, ali NE šalji na FINA.
Spremi generirane datoteke:
- XML racun: invoice_001_URED_1_2026-01-27.xml
- XAdES potpis: invoice_001_URED_1_2026-01-27_signed.xml

Certifikat: 47034854402.F1.1.p12
Lozinka: NinuPiL1903
"""

    try:
        print("\n[PROCESSING] Calling Fiskalni Executor directly...")

        # Get the executor agent from worker_agents list
        executor = None
        for agent in system.worker_agents:
            if 'fiskalni_executor' in agent.name.lower() or 'executor' in agent.name.lower():
                executor = agent
                break

        if not executor:
            print("\n[ERROR] Fiskalni Executor agent not found!")
            print(f"Available agents: {[a.name for a in system.worker_agents]}")
            return

        print(f"[OK] Executor agent loaded: {executor.name}")

        # Create a runner for the executor
        from agents.adk_agents.runner_utils import RunnerHelper
        executor_runner = RunnerHelper(
            agent=executor,
            session_id=system.session_id,
            user_id=system.user_id
        )

        # Run the executor
        print("\n[PROCESSING] Executor is generating XML and XAdES signature...")
        response = await executor_runner.run(query)

        print(sanitize_emojis(f"\n[OK] Executor Result:\n{response}"))

        # Check for success indicators
        if "XML" in response or "xml" in response:
            print("\n[OK] XML generation mentioned!")
        else:
            print("\n[WARNING] No XML generation mentioned")

        if any(word in response.lower() for word in ["potpis", "sign", "xades", "signature"]):
            print("[OK] XAdES signing mentioned!")
        else:
            print("[WARNING] No signing mentioned")

    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*80)

    # ========================================================================
    # TEST 2: Check for Generated Files
    # ========================================================================
    print("\nTEST 2: Checking for Generated XML Files")
    print("="*80)

    project_root = Path(__file__).parent
    xml_files = list(project_root.glob("**/*.xml"))

    if xml_files:
        print(f"\n[OK] Found {len(xml_files)} XML file(s):")
        for xml_file in xml_files[-5:]:  # Show last 5
            size_kb = xml_file.stat().st_size / 1024
            print(f"  - {xml_file.name} ({size_kb:.2f} KB)")

            # Try to read and validate XML structure
            try:
                content = xml_file.read_text(encoding='utf-8')
                if 'Invoice' in content or 'RacunZahtjev' in content:
                    print(f"    [OK] Contains invoice data")
                if 'Signature' in content or 'ds:Signature' in content:
                    print(f"    [OK] Contains signature")
            except Exception as e:
                print(f"    [WARNING] Could not read file: {e}")
    else:
        print("\n[WARNING] No XML files found")

    print("\n" + "="*80)
    print("Test Complete!")
    print("="*80)

    print("\nSummary:")
    print("1. This test bypasses Pripremac/Validator pipeline")
    print("2. Calls Executor directly with pre-validated data")
    print("3. Tests XML generation (build_ubl_invoice)")
    print("4. Tests XAdES signing (sign_xml_xades)")
    print("5. Does NOT test SOAP communication to FINA")


if __name__ == "__main__":
    asyncio.run(test_executor_direct())
