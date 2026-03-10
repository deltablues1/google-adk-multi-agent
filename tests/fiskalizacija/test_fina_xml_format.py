"""
Test FINA XML Format Generation

Tests the new build_ubl_invoice wrapper that generates FINA RacunZahtjev format.
"""
import asyncio
import sys
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

sys.path.insert(0, str(Path(__file__).parent))

from tools.adk_tools.fiskalizacija_adk_tools import (
    load_certificate,
    calculate_zki,
    build_ubl_invoice
)


async def test_fina_xml_generation():
    """Test complete flow: cert -> ZKI -> XML"""

    print("=" * 80)
    print("FINA XML FORMAT GENERATION TEST")
    print("=" * 80)
    print()

    # Test data
    invoice_data = {
        "invoice_number": "001/DEMO/1",
        "issue_date": "2026-01-29",
        "issue_time": "14:00:00",
        "supplier": {
            "name": "LUX TECH D.O.O.",
            "oib": "47034854402",
            "address": "Test ulica 1",
            "city": "Hrvatski Leskovac",
            "postal_code": "10000",
            "country_code": "HR"
        },
        "tax_breakdown": {
            "subtotals": [
                {
                    "vat_rate": "25",
                    "taxable_amount": "1500.00",
                    "tax_amount": "375.00"
                }
            ],
            "total_net": "1500.00",
            "total_tax": "375.00",
            "total_gross": "1875.00"
        },
        "payment_means_code": "10"  # Cash
    }

    # Step 1: Load certificate
    print("[1] Loading certificate...")
    cert_result = await load_certificate(
        certificate_name="47034854402.F1.1.p12",
        cert_password=""
    )

    if not cert_result.get("success"):
        print(f"❌ Certificate loading failed: {cert_result.get('error')}")
        return False

    print(f"✅ Certificate loaded: {cert_result.get('subject')}")
    print()

    # Step 2: Calculate ZKI
    print("[2] Calculating ZKI...")
    zki_result = await calculate_zki(
        oib="47034854402",
        invoice_datetime="2026-01-29T14:00:00",
        invoice_number="001/DEMO/1",
        business_unit="DEMO",
        device_number="1",
        total_amount="1875.00",
        private_key=cert_result.get("private_key")
    )

    if not zki_result.get("success"):
        print(f"❌ ZKI calculation failed: {zki_result.get('error')}")
        return False

    zki = zki_result.get("zki")
    print(f"✅ ZKI calculated: {zki}")
    print()

    # Step 3: Build FINA XML (now with ZKI!)
    print("[3] Building FINA RacunZahtjev XML...")
    invoice_data["zki"] = zki  # ← Include ZKI!

    xml_result = await build_ubl_invoice(invoice_data)

    if not xml_result.get("success"):
        print(f"❌ XML generation failed: {xml_result.get('error')}")
        return False

    xml = xml_result.get("xml")
    print(f"✅ XML generated: {len(xml)} bytes")
    print()

    # Step 4: Verify XML structure
    print("[4] Verifying XML structure...")
    checks = [
        ("<?xml version", "XML declaration"),
        ("<RacunZahtjev", "RacunZahtjev root element"),
        ("http://www.apis-it.hr/fin/2012/types/f73", "FINA namespace"),
        ("<Zaglavlje>", "Zaglavlje element"),
        ("<IdPoruke>", "IdPoruke element"),
        ("<Racun>", "Racun element"),
        ("<Oib>47034854402</Oib>", "OIB element"),
        (f"<ZastKod>{zki.replace('-', '').lower()}</ZastKod>", "ZKI element"),
        ("<IznosUkupno>1875.00</IznosUkupno>", "Total amount"),
        ("<NacinPlac>G</NacinPlac>", "Payment method (Cash)"),
    ]

    all_passed = True
    for check_str, description in checks:
        if check_str in xml:
            print(f"  ✅ {description}")
        else:
            print(f"  ❌ {description} - NOT FOUND")
            all_passed = False

    print()

    if not all_passed:
        print("❌ XML verification FAILED!")
        print()
        print("Generated XML (first 2000 chars):")
        print("-" * 80)
        print(xml[:2000])
        print("-" * 80)
        return False

    print("✅ XML verification PASSED!")
    print()

    # Step 5: Show XML sample
    print("[5] XML Sample (first 1000 chars):")
    print("-" * 80)
    print(xml[:1000])
    print("-" * 80)
    print()

    print("=" * 80)
    print("✅ TEST PASSED - FINA XML FORMAT IS CORRECT!")
    print("=" * 80)
    print()
    print("Next step: Test with real FINA DEMO submission")
    print("Run: python test_fiskalizacija_full.py")

    return True


if __name__ == "__main__":
    result = asyncio.run(test_fina_xml_generation())
    sys.exit(0 if result else 1)
