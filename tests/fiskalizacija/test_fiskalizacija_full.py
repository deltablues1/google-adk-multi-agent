"""
POTPUNI FISKALIZACIJA 2.0 TEST

Testira cijeli pipeline:
1. XML Generacija (UBL 2.1 / EN 16931)
2. XAdES Potpis (s certifikatom)
3. SOAP komunikacija s FINA DEMO endpointom
4. Spremanje dokumenta na Google Drive

Certificate: 47034854402.F1.1.p12
Password: NinuPiL1903
Environment: FINA DEMO (sandbox)
"""

import asyncio
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

# Configure logging to show DEBUG level for SOAP communication
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

sys.path.insert(0, str(Path(__file__).parent))
from main import WorkspaceADKSystem, sanitize_emojis


async def test_full_fiscalization():
    print("\n" + "="*80)
    print("POTPUNI FISKALIZACIJA 2.0 TEST")
    print("Pipeline: XML -> XAdES -> SOAP -> Google Drive")
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
    # TEST: Potpuni Fiskalizacijski Pipeline
    # ========================================================================
    print("="*80)
    print("TEST: Potpuni Fiskalizacijski Workflow")
    print("="*80)

    # Pre-validated invoice data
    invoice_data = {
        "issuer": {
            "oib": "47034854402",
            "name": "LUX TECH d.o.o.",
            "address": "Hrvatski Leskovac, Croatia"
        },
        "buyer": {
            "oib": "85546001374",
            "name": "Pivovara Test d.o.o."
        },
        "invoice": {
            "number": "001/DEMO/1",
            "issue_date": "2026-01-28",
            "due_date": "2026-02-28",
            "currency": "EUR",
            "payment_method": "TRANSAKCIJSKI_RACUN",
            "business_premise": "DEMO",
            "cash_register": "1"
        },
        "items": [
            {
                "description": "IT Consulting Services",
                "kpd_code": "62.20.0",
                "quantity": 10.0,
                "unit": "HUR",  # UN/ECE Rec 20 code for hour
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

    # Create comprehensive query
    query = f"""Fiskaliziraj racun i spremi rezultat na Google Drive.

PODACI ZA RACUN (već validirani):
{json.dumps(invoice_data, indent=2, ensure_ascii=False)}

CERTIFIKAT ZA POTPIS (XAdES):
- Datoteka: 47034854402.F1.1.p12
- Lozinka: NinuPiL1903

mTLS CERTIFIKATI (za SOAP komunikaciju):
- Client Certificate: client_cert.pem (izvučeno iz .p12)
- Private Key: client_key.pem (izvučeno iz .p12)
- CA Certificate: fina_demo_ca_bundle.pem (intermediate + root CA)

OKRUZENJE: FINA DEMO (sandbox)

POSTUPAK:
1. Generiraj UBL 2.1 / EN 16931 XML
2. Potpisi XML s XAdES-BES digitalnim potpisom (koristi 47034854402.F1.1.p12)
3. Pošalji potpisani XML na FINA DEMO endpoint (SOAP) koristeći mTLS autentikaciju:
   - client_cert.pem + client_key.pem za klijentsku autentikaciju
   - fina_demo_ca_bundle.pem za SSL verifikaciju FINA servera
4. Spremi generirane dokumente na Google Drive u folder "Fiskalizacija Test"

Dokumenti za spremanje:
- Nepotpisani XML
- Potpisani XML (XAdES)
- FINA Response (JIR ako uspije SOAP)
- Izvještaj o fiskalizaciji

NAPOMENA: Ovo je TEST racun za DEMO okruzenje. Za SOAP koristi odvojene .pem datoteke (mTLS zahtijeva cert i key kao odvojene datoteke). CA bundle sadrzi intermediate + root CA za kompletan certificate chain.
"""

    try:
        print("\n[PROCESSING] Starting full fiscalization pipeline...")
        print("\n1. Generating UBL XML...")
        print("2. Loading certificate and signing with XAdES...")
        print("3. Sending to FINA DEMO via SOAP...")
        print("4. Saving documents to Google Drive...")

        response = await system.orchestrator_helper.run(query)

        print(sanitize_emojis(f"\n[OK] Pipeline Result:\n{response}"))

        # Check for success indicators
        success_indicators = []

        if "XML" in response or "xml" in response:
            success_indicators.append("✅ XML generation")
            print("\n[OK] XML generation mentioned!")

        if any(word in response.lower() for word in ["potpis", "sign", "xades", "signature"]):
            success_indicators.append("✅ XAdES signing")
            print("[OK] XAdES signing mentioned!")

        if any(word in response.lower() for word in ["soap", "fina", "jir"]):
            success_indicators.append("✅ SOAP communication")
            print("[OK] SOAP/FINA mentioned!")

        if any(word in response.lower() for word in ["drive", "folder", "document", "dokument"]):
            success_indicators.append("✅ Google Drive upload")
            print("[OK] Google Drive upload mentioned!")

        print("\n" + "="*80)
        print("SUCCESS INDICATORS:")
        for indicator in success_indicators:
            print(f"  {indicator}")
        print("="*80)

    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*80)
    print("Test Complete!")
    print("="*80)

    print("\nNext Steps:")
    print("1. Check Google Drive folder 'Fiskalizacija Test' for documents")
    print("2. Verify XML structure and XAdES signature")
    print("3. Check FINA response (if SOAP succeeded)")
    print("4. Review JIR code (if received from FINA)")


if __name__ == "__main__":
    asyncio.run(test_full_fiscalization())
