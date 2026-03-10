"""
End-to-End Fiskalizacija Test

Full workflow test: Pripremac -> Validator -> Executor
Tests XML generation, XAdES signing, and (optionally) SOAP to FINA DEMO

Uses VALID data to ensure full pipeline execution.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from main import WorkspaceADKSystem, sanitize_emojis


async def test_full_invoice_pipeline():
    print("\n" + "="*80)
    print("END-TO-END FISKALIZACIJA TEST")
    print("Full Pipeline: Pripremac -> Validator -> Executor")
    print("="*80)

    # Initialize system
    print("\nInitializing system...")
    system = WorkspaceADKSystem()
    system.initialize_agents()

    print(f"\n[OK] System initialized")
    print(f"Session: {system.session_id}")
    print(f"Certificate: 47034854402.F1.1.p12")

    # Verify certificate exists
    cert_file = Path(__file__).parent / "47034854402.F1.1.p12"
    if not cert_file.exists():
        print(f"\n[ERROR] Certificate not found: {cert_file}")
        return
    print(f"[OK] Certificate found\n")

    # ========================================================================
    # TEST 1: Simple Invoice - VALID DATA (should pass through all 3 agents)
    # ========================================================================
    print("="*80)
    print("TEST 1: Simple Invoice with VALID Data")
    print("Expected: Pripremac -> Validator -> Executor -> XML + Signature")
    print("="*80)

    # IMPORTANT: Using VALID OIBs, correct invoice format, and EXPLICIT KPD code
    query = """Fiskaliziraj racun sa sljedecim podacima:

IZDAVATELJ:
- OIB: 47034854402
- Naziv: Test Company d.o.o.
- Adresa: Testna 1, Zagreb

KUPAC:
- OIB: 85546001374
- Naziv: Pivovara Test d.o.o.

RACUN:
- Broj racuna: 001/URED/1
- Datum izdavanja: 2026-01-27
- Datum dospijeća: 2026-02-27

STAVKE:
- Stavka 1: Usluga IT konzultacija
  - KPD kod: 62.20.0
  - Kolicina: 10 sati
  - Jedinicna cijena: 150.00 EUR
  - Jedinica: sat

PDV: 25%
Nacin placanja: Transakcijski racun
Poslovni prostor: URED
Naplatni uredjaj: 1

NAPOMENA: Ovo je TEST racun za DEMO okruzenje.
Generiraj XML, potpisi ga s certifikatom, ali NE salji na FINA (DEMO mode).
Spremi XML i potpis u fajlove za pregled.
"""

    try:
        print("\n[PROCESSING] Starting full 3-agent pipeline...")
        response = await system.orchestrator_helper.run(query)
        print(sanitize_emojis(f"\n[OK] Pipeline Result:\n{response}"))

        # Check if we got XML and signature
        if "XML" in response or "xml" in response:
            print("\n[OK] XML generation mentioned in response!")
        else:
            print("\n[WARNING] No XML generation mentioned - may have stopped at validation")

        if "potpis" in response.lower() or "sign" in response.lower() or "xades" in response.lower():
            print("[OK] XAdES signing mentioned in response!")
        else:
            print("[WARNING] No signing mentioned - may not have reached Executor")

    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*80)

    # ========================================================================
    # TEST 2: Check for generated files
    # ========================================================================
    print("\nTEST 2: Checking for Generated Files")
    print("="*80)

    # Look for XML files
    project_root = Path(__file__).parent
    xml_files = list(project_root.glob("**/*.xml"))

    if xml_files:
        print(f"\n[OK] Found {len(xml_files)} XML file(s):")
        for xml_file in xml_files[-5:]:  # Show last 5
            print(f"  - {xml_file.name}")
    else:
        print("\n[WARNING] No XML files found")

    print("\n" + "="*80)
    print("Test Complete!")
    print("="*80)

    print("\nNext Steps:")
    print("1. Review the response above")
    print("2. Check if XML was generated")
    print("3. Check if XAdES signature was created")
    print("4. Verify certificate was used for signing")
    print("5. If successful, ready for PTS testing!")


if __name__ == "__main__":
    asyncio.run(test_full_invoice_pipeline())
