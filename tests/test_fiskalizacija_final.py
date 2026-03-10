"""
FINA Fiskalizacija - Final Integrated Test

This test demonstrates the complete fiscalization flow using all production modules:
1. Load certificate from .p12 file
2. Calculate ZKI
3. Build RacunZahtjev XML
4. Sign with FINA-compatible signature (RSA-SHA1, exc-c14n)
5. Send to FINA sandbox
6. Receive JIR

Usage:
    python tests/test_fiskalizacija_final.py          # Interactive mode
    python tests/test_fiskalizacija_final.py --auto   # Auto-confirm

This test has been VERIFIED to work with FINA sandbox - JIR successfully received.
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
import tempfile

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configuration
CERT_PATH = project_root / "47034854402.F1.1.p12"
CERT_PASSWORD = "NinuPiL1903"

FINA_SANDBOX_URL = "https://cistest.apis-it.hr:8449/FiskalizacijaServiceTest"


def main():
    """Run complete fiscalization test."""
    # Import production modules
    from config.company_config import get_company_config
    from tools.api_implementations.xades_signer import (
        load_certificate_from_file,
        calculate_zki,
        sign_fina_xml
    )
    from tools.api_implementations.fina_xml_builder import build_racun_zahtjev
    from tools.api_implementations.fina_soap_client import (
        build_fiscalization_request,
        parse_fina_response
    )

    # Also need requests and cryptography for sending
    import requests
    import urllib3
    from cryptography.hazmat.primitives import serialization

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # Get company config
    config = get_company_config()
    now = datetime.now()

    print("=" * 70)
    print("   FINA FISKALIZACIJA - ZAVRŠNI INTEGRIRANI TEST")
    print("=" * 70)
    print(f"Vrijeme: {now.strftime('%d.%m.%Y %H:%M:%S')}")
    print(f"Tvrtka: {config.name}")
    print(f"OIB: {config.oib}")
    print(f"Okruženje: Sandbox")
    print()

    # Step 1: Load certificate
    print("[1/6] Učitavanje certifikata...")
    try:
        cert_info = load_certificate_from_file(str(CERT_PATH), CERT_PASSWORD)
        print(f"      OK - {cert_info.subject}")
        print(f"      Vrijedi do: {cert_info.valid_to.strftime('%d.%m.%Y')}")
    except Exception as e:
        print(f"      GREŠKA: {e}")
        return 1

    # Step 2: Generate invoice data
    print("\n[2/6] Generiranje podataka računa...")
    broj_racuna = now.strftime("%y%m%d%H%M%S")
    oznaka_pp = "1"  # Business premises
    oznaka_nu = "1"  # Cash register
    datum_vrijeme = now

    neto = Decimal("100.00")
    pdv_stopa = Decimal("25.00")
    pdv_iznos = neto * pdv_stopa / 100
    ukupno = neto + pdv_iznos

    print(f"      Broj: {broj_racuna}/{oznaka_pp}/{oznaka_nu}")
    print(f"      Datum: {datum_vrijeme.strftime('%d.%m.%Y %H:%M:%S')}")
    print(f"      Neto: {neto:.2f} EUR")
    print(f"      PDV ({pdv_stopa}%): {pdv_iznos:.2f} EUR")
    print(f"      Ukupno: {ukupno:.2f} EUR")

    # Step 3: Calculate ZKI
    print("\n[3/6] Izračun ZKI...")
    try:
        zki = calculate_zki(
            oib=config.oib,
            invoice_datetime=datum_vrijeme,
            invoice_number=broj_racuna,
            business_unit=oznaka_pp,
            device_number=oznaka_nu,
            total_amount=ukupno,
            private_key=cert_info.private_key
        )
        print(f"      OK - ZKI: {zki}")
    except Exception as e:
        print(f"      GREŠKA: {e}")
        return 1

    # Step 4: Build RacunZahtjev XML
    print("\n[4/6] Generiranje RacunZahtjev XML...")
    try:
        racun_xml = build_racun_zahtjev(
            oib=config.oib,
            u_sustavu_pdv=True,
            datum_vrijeme=datum_vrijeme,
            oznaka_slijednosti="P",
            broj_racuna=broj_racuna,
            oznaka_poslovnog_prostora=oznaka_pp,
            oznaka_naplatnog_uredaja=oznaka_nu,
            ukupan_iznos=str(ukupno),
            nacin_placanja="G",  # Gotovina
            oib_operatera=config.oib,
            zki=zki,
            pdv=[{
                "stopa": str(pdv_stopa),
                "osnovica": str(neto),
                "iznos": str(pdv_iznos)
            }],
            naknadna_dostava=False
        )
        print(f"      OK - XML generiran ({len(racun_xml)} bytes)")
    except Exception as e:
        print(f"      GREŠKA: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Step 5: Sign XML
    print("\n[5/6] Digitalno potpisivanje (RSA-SHA1, exc-c14n)...")
    try:
        signed_xml = sign_fina_xml(
            racun_xml,
            cert_info.private_key,
            cert_info.certificate
        )
        print(f"      OK - Potpisan XML ({len(signed_xml)} bytes)")
    except Exception as e:
        print(f"      GREŠKA: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Preview
    print("\n" + "-" * 70)
    print("PREGLED POTPISANOG XML-a")
    print("-" * 70)
    # Show first 1500 chars
    preview = signed_xml[:1500]
    print(preview)
    if len(signed_xml) > 1500:
        print(f"... ({len(signed_xml) - 1500} znakova više)")
    print("-" * 70)

    # Confirmation
    print("\n" + "=" * 70)
    print("PREGLED PRIJE SLANJA")
    print("=" * 70)
    print(f"Račun: {broj_racuna}/{oznaka_pp}/{oznaka_nu}")
    print(f"ZKI: {zki}")
    print(f"Iznos: {ukupno:.2f} EUR")
    print(f"Endpoint: {FINA_SANDBOX_URL}")
    print()

    # Auto-confirm check
    if len(sys.argv) > 1 and sys.argv[1] == "--auto":
        confirm = "da"
        print("Auto-confirm enabled")
    else:
        try:
            confirm = input("Poslati na FINA sandbox? (da/ne): ").strip().lower()
        except EOFError:
            confirm = "da"
            print("Auto-confirm (non-interactive)")

    if confirm != "da":
        print("\nOtkazano.")
        return 0

    # Step 6: Send to FINA
    print("\n[6/6] Slanje na FINA sandbox...")
    try:
        # Build SOAP envelope
        soap_message = build_fiscalization_request(signed_xml)

        # Create temp PEM file for mTLS
        key_pem = cert_info.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )
        cert_pem = cert_info.certificate.public_bytes(serialization.Encoding.PEM)

        with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as f:
            f.write(cert_pem)
            f.write(key_pem)
            combined_pem = f.name

        try:
            # Send request
            session = requests.Session()
            session.cert = combined_pem
            session.verify = False

            response = session.post(
                FINA_SANDBOX_URL,
                data=soap_message.encode('utf-8'),
                headers={'Content-Type': 'text/xml; charset=utf-8'},
                timeout=30
            )

            print(f"      HTTP Status: {response.status_code}")

            # Parse response
            result = parse_fina_response(response.text)

        finally:
            os.unlink(combined_pem)

    except Exception as e:
        print(f"      GREŠKA pri slanju: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Display result
    print()
    if result.get("success"):
        jir = result.get("jir")
        print("=" * 70)
        print("          FISKALIZACIJA USPJESNA!")
        print("=" * 70)
        print()
        print(f"  JIR:    {jir}")
        print(f"  ZKI:    {zki}")
        print(f"  Račun:  {broj_racuna}/{oznaka_pp}/{oznaka_nu}")
        print(f"  Iznos:  {ukupno:.2f} EUR")
        print(f"  Datum:  {datum_vrijeme.strftime('%d.%m.%Y %H:%M:%S')}")
        print()
        print("=" * 70)

        # Save to file for reference
        result_file = project_root / "tests" / f"jir_{broj_racuna}.txt"
        with open(result_file, "w", encoding="utf-8") as f:
            f.write(f"FISKALIZACIJA USPJEŠNA\n")
            f.write(f"======================\n\n")
            f.write(f"Datum: {datum_vrijeme.strftime('%d.%m.%Y %H:%M:%S')}\n")
            f.write(f"Račun: {broj_racuna}/{oznaka_pp}/{oznaka_nu}\n")
            f.write(f"JIR: {jir}\n")
            f.write(f"ZKI: {zki}\n")
            f.write(f"Iznos: {ukupno:.2f} EUR\n")
            f.write(f"\nOdgovor servera:\n")
            f.write(response.text)
        print(f"Rezultat spremljen: {result_file}")

        return 0
    else:
        print("=" * 70)
        print("          FISKALIZACIJA NIJE USPJELA")
        print("=" * 70)
        print()
        print("Greške:")
        for err in result.get("errors", []):
            print(f"  [{err.get('code', 'N/A')}] {err.get('message', 'N/A')}")
        print()
        print("Odgovor servera:")
        print(response.text[:2000])
        return 1


if __name__ == "__main__":
    sys.exit(main())
