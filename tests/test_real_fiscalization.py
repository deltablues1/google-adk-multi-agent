"""
PRAVI TEST FISKALIZACIJE - FINA Sandbox

Ovaj test šalje pravi račun na FINA CIS sandbox i dobiva JIR.

NAPOMENA: Ovo je TESTNO okruženje, računi nisu stvarni.

Run with: python tests/test_real_fiscalization.py
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
import asyncio

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configuration
CERT_PATH = project_root / "47034854402.F1.1.p12"
CERT_PASSWORD = os.environ.get("FINA_CERT_PASSWORD")


async def create_test_invoice():
    """Create a test invoice for fiscalization."""
    from config.company_config import get_company_config
    from tools.adk_tools.fiskalizacija_adk_tools import (
        load_certificate,
        validate_oib,
        calculate_tax,
        build_ubl_invoice,
        calculate_zki,
        sign_xades,
        check_invoice_ledger,
        save_invoice_ledger,
    )

    config = get_company_config()
    now = datetime.now(timezone.utc)

    print("="*70)
    print("FISKALIZACIJA - PRAVI TEST NA FINA SANDBOX")
    print("="*70)
    print(f"Vrijeme: {now.strftime('%d.%m.%Y %H:%M:%S')}")
    print(f"Tvrtka: {config.name}")
    print(f"OIB: {config.oib}")
    print()

    # Step 1: Load certificate
    print("[1/8] Učitavanje certifikata...")
    cert_result = await load_certificate(
        source=str(CERT_PATH),
        password=CERT_PASSWORD,
        source_type="file",
        cache_key="fina-prod-test"
    )

    if not cert_result["success"]:
        print(f"    GREŠKA: {cert_result.get('error')}")
        return None
    print(f"    OK - Certifikat učitan: {cert_result['certificate_info'].get('subject')}")

    # Step 2: Validate OIB
    print("\n[2/8] Validacija OIB-a...")
    oib_result = await validate_oib(config.oib)
    if not oib_result["valid"]:
        print(f"    GREŠKA: {oib_result.get('error_message')}")
        return None
    print(f"    OK - OIB validan: {config.oib}")

    # Step 3: Generate invoice number
    print("\n[3/8] Generiranje broja računa...")
    # Format: BROJ/POSLOVNI_PROSTOR/NAPLATNI_UREDAJ
    sequential = now.strftime("%y%m%d%H%M")  # Unique based on time
    business_unit = config.business_premises[0].code
    device = config.cash_registers[0].code
    invoice_number = f"{sequential}/{business_unit}/{device}"
    print(f"    OK - Broj računa: {invoice_number}")

    # Check if already fiscalized (idempotency)
    print("\n[4/8] Provjera postojećeg računa...")
    ledger_check = await check_invoice_ledger(invoice_number, config.oib)
    if ledger_check.get("exists"):
        print(f"    INFO - Račun već fiskaliziran, JIR: {ledger_check.get('jir')}")
        return ledger_check

    print("    OK - Račun nije prethodno fiskaliziran")

    # Step 5: Calculate tax
    print("\n[5/8] Izračun poreza...")
    invoice_items = [
        {
            "description": "Elektroinstalacijski radovi - ugradnja rasvjete",
            "quantity": "1",
            "unit": "HUR",
            "unit_price": "100.00",
            "net_amount": "100.00",
            "vat_rate": "25"
        }
    ]

    tax_result = await calculate_tax([
        {"net_amount": "100.00", "vat_rate": "25"}
    ])
    print(f"    Neto iznos:  {tax_result['total_net']} EUR")
    print(f"    PDV (25%):   {tax_result['total_tax']} EUR")
    print(f"    Ukupno:      {tax_result['total_gross']} EUR")

    # Step 6: Build UBL Invoice
    print("\n[6/8] Generiranje UBL XML računa...")
    invoice_data = {
        "invoice_number": invoice_number,
        "invoice_type": "380",  # Commercial invoice
        "issue_date": now.strftime("%Y-%m-%d"),
        "issue_time": now.strftime("%H:%M:%S"),
        "due_date": now.strftime("%Y-%m-%d"),
        "currency": "EUR",
        "supplier": {
            "name": config.name,
            "oib": config.oib,
            "vat_number": f"HR{config.oib}",
            "address": config.address,
            "city": config.city,
            "postal_code": config.postal_code,
            "country_code": config.country_code
        },
        "customer": {
            "name": "TEST KUPAC D.O.O.",
            "oib": "12345678903",  # Test OIB
            "vat_number": "HR12345678903",
            "address": "Testna ulica 1",
            "city": "Zagreb",
            "postal_code": "10000",
            "country_code": "HR"
        },
        "items": [
            {
                "line_id": "1",
                "description": "Elektroinstalacijski radovi - ugradnja rasvjete",
                "quantity": "1",
                "unit": "HUR",
                "unit_price": "100.00",
                "net_amount": "100.00",
                "vat_rate": "25",
                "vat_amount": "25.00",
                "gross_amount": "125.00",
                "nkd_code": "43.21"  # Elektroinstalacijski radovi
            }
        ],
        "tax_breakdown": tax_result,
        "payment_means_code": "30",  # Credit transfer
        "note": "Testni račun - FINA Sandbox"
    }

    ubl_result = await build_ubl_invoice(invoice_data)
    if not ubl_result["success"]:
        print(f"    GREŠKA: {ubl_result.get('error')}")
        return None
    print(f"    OK - UBL XML generiran ({len(ubl_result['xml'])} bytes)")

    # Step 7: Calculate ZKI
    print("\n[7/8] Izračun ZKI (Zaštitni Kod Izdavatelja)...")
    zki_result = await calculate_zki(
        oib=config.oib,
        invoice_datetime=now.isoformat(),
        invoice_number=sequential,
        business_unit=business_unit,
        device_number=device,
        total_amount=tax_result["total_gross"],
        cert_cache_key="fina-prod-test"
    )

    if not zki_result["success"]:
        print(f"    GREŠKA: {zki_result.get('error')}")
        return None
    zki = zki_result["zki"]
    print(f"    OK - ZKI: {zki}")

    # Step 8: Sign XML with XAdES-BES
    print("\n[8/8] Digitalno potpisivanje (XAdES-BES)...")
    sign_result = await sign_xades(
        xml=ubl_result["xml"],
        cert_cache_key="fina-prod-test"
    )

    if not sign_result["success"]:
        print(f"    GREŠKA: {sign_result.get('error')}")
        return None
    signed_xml = sign_result["signed_xml"]
    print(f"    OK - XML potpisan ({len(signed_xml)} bytes)")

    return {
        "invoice_number": invoice_number,
        "invoice_data": invoice_data,
        "signed_xml": signed_xml,
        "zki": zki,
        "tax": tax_result
    }


async def send_to_fina(invoice_data: dict):
    """Send the invoice to FINA sandbox."""
    import requests
    import tempfile
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    import urllib3

    # Disable SSL warnings for sandbox
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    print("\n" + "="*70)
    print("SLANJE NA FINA CIS SANDBOX")
    print("="*70)

    endpoint = "https://cistest.apis-it.hr:8449/FiskalizacijaServiceTest"
    print(f"Endpoint: {endpoint}")
    print(f"Račun: {invoice_data['invoice_number']}")
    print(f"ZKI: {invoice_data['zki']}")
    print(f"Iznos: {invoice_data['tax']['total_gross']} EUR")

    # Load certificate
    with open(CERT_PATH, 'rb') as f:
        p12_data = f.read()

    private_key, certificate, chain = pkcs12.load_key_and_certificates(
        p12_data, CERT_PASSWORD.encode('utf-8'), default_backend()
    )

    # Export to PEM
    key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )
    cert_pem = certificate.public_bytes(serialization.Encoding.PEM)

    # Create temp combined PEM file
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as f:
        f.write(cert_pem)
        f.write(key_pem)
        combined_pem = f.name

    try:
        # Build SOAP envelope
        from tools.api_implementations.fina_soap_client import build_fiscalization_request

        soap_message = build_fiscalization_request(
            signed_invoice_xml=invoice_data["signed_xml"],
            message_id=f"MSG-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )

        print(f"\nŠaljem SOAP zahtjev ({len(soap_message)} bytes)...")

        session = requests.Session()
        session.cert = combined_pem
        session.verify = False  # Sandbox uses self-signed certs

        response = session.post(
            endpoint,
            data=soap_message.encode('utf-8'),
            headers={
                'Content-Type': 'application/soap+xml; charset=utf-8',
                'SOAPAction': 'http://www.apis-it.hr/fin/2012/types/f73/RacunZahtjev'
            },
            timeout=30
        )

        print(f"HTTP Status: {response.status_code}")

        # Parse response
        from tools.api_implementations.fina_soap_client import parse_fina_response

        result = parse_fina_response(response.text)

        print("\n" + "-"*70)
        if result["success"]:
            print("FISKALIZACIJA USPJEŠNA!")
            print("-"*70)
            print(f"JIR: {result['jir']}")
            print(f"ZKI: {result.get('zki', invoice_data['zki'])}")
            print(f"Timestamp: {result.get('timestamp', 'N/A')}")
        else:
            print("FISKALIZACIJA NIJE USPJELA")
            print("-"*70)
            if result.get("errors"):
                for err in result["errors"]:
                    print(f"Greška {err.get('code', 'N/A')}: {err.get('message', 'N/A')}")
            print(f"\nRaw response:\n{response.text[:1000]}")

        return result

    finally:
        os.unlink(combined_pem)


async def main():
    """Main test function."""
    print("\n" + "#"*70)
    print("#" + " "*20 + "FISKALIZACIJA TEST" + " "*20 + "#")
    print("#"*70 + "\n")

    # Create invoice
    invoice = await create_test_invoice()

    if invoice is None:
        print("\n[GREŠKA] Nije moguće kreirati račun")
        return 1

    if invoice.get("jir"):
        # Already fiscalized
        print("\n[INFO] Račun je već fiskaliziran")
        return 0

    # Confirmation before sending
    print("\n" + "="*70)
    print("PREGLED PRIJE SLANJA")
    print("="*70)
    print(f"Broj računa: {invoice['invoice_number']}")
    print(f"ZKI: {invoice['zki']}")
    print(f"Iznos: {invoice['tax']['total_gross']} EUR")
    print(f"XML veličina: {len(invoice['signed_xml'])} bytes")
    print()

    # Ask for confirmation
    confirm = input("Želite li poslati račun na FINA sandbox? (da/ne): ").strip().lower()

    if confirm != "da":
        print("\nOtkazano.")
        return 0

    # Send to FINA
    result = await send_to_fina(invoice)

    if result and result.get("success"):
        # Save to ledger
        from tools.adk_tools.fiskalizacija_adk_tools import save_invoice_ledger
        from config.company_config import get_company_config

        config = get_company_config()

        save_result = await save_invoice_ledger(
            invoice_number=invoice["invoice_number"],
            supplier_oib=config.oib,
            jir=result["jir"],
            zki=invoice["zki"],
            signed_xml=invoice["signed_xml"],
            fina_response=str(result),
            total_amount=invoice["tax"]["total_gross"]
        )

        if save_result["success"]:
            print(f"\n[OK] Račun spremljen u ledger")

        print("\n" + "="*70)
        print("SAŽETAK")
        print("="*70)
        print(f"Račun:  {invoice['invoice_number']}")
        print(f"JIR:    {result['jir']}")
        print(f"ZKI:    {invoice['zki']}")
        print(f"Iznos:  {invoice['tax']['total_gross']} EUR")
        print("="*70)

        return 0
    else:
        print("\n[GREŠKA] Fiskalizacija nije uspjela")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
