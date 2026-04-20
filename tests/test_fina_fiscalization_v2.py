"""
FINA Fiskalizacija Test v2 - Pravilni FINA XML format

Ovaj test koristi ispravni FINA XML format prema specifikaciji:
http://www.apis-it.hr/fin/2012/types/f73

Run with: python tests/test_fina_fiscalization_v2.py
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
import asyncio
import uuid

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

CERT_PATH = project_root / "47034854402.F1.1.p12"
CERT_PASSWORD = os.environ.get("FINA_CERT_PASSWORD")


def sign_racun_zahtjev(xml_str: str) -> str:
    """Sign the RacunZahtjev XML with XAdES-BES signature."""
    from tools.api_implementations.xades_signer import (
        load_certificate_from_file,
        XAdESSigner
    )

    cert_info = load_certificate_from_file(str(CERT_PATH), CERT_PASSWORD)
    signer = XAdESSigner(cert_info)
    signed_xml = signer.sign(xml_str)
    return signed_xml


def send_to_fina_sandbox(signed_xml: str) -> dict:
    """Send signed XML to FINA sandbox."""
    import requests
    import tempfile
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    import urllib3
    import re

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    endpoint = "https://cistest.apis-it.hr:8449/FiskalizacijaServiceTest"

    # Load certificate
    with open(CERT_PATH, 'rb') as f:
        p12_data = f.read()

    private_key, certificate, chain = pkcs12.load_key_and_certificates(
        p12_data, CERT_PASSWORD.encode('utf-8'), default_backend()
    )

    key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )
    cert_pem = certificate.public_bytes(serialization.Encoding.PEM)

    with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as f:
        f.write(cert_pem)
        f.write(key_pem)
        combined_pem = f.name

    try:
        # Wrap in SOAP envelope
        inner_xml = re.sub(r'<\?xml[^?]*\?>\s*', '', signed_xml)

        soap_envelope = f'''<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
    <soapenv:Body>
        {inner_xml}
    </soapenv:Body>
</soapenv:Envelope>'''

        session = requests.Session()
        session.cert = combined_pem
        session.verify = False

        response = session.post(
            endpoint,
            data=soap_envelope.encode('utf-8'),
            headers={
                'Content-Type': 'text/xml; charset=utf-8',
                'SOAPAction': ''
            },
            timeout=30
        )

        return {
            "status_code": response.status_code,
            "response_text": response.text,
            "success": response.status_code == 200
        }

    finally:
        os.unlink(combined_pem)


def parse_fina_response(response_text: str) -> dict:
    """Parse FINA response to extract JIR or errors."""
    from lxml import etree
    from io import BytesIO

    try:
        doc = etree.parse(BytesIO(response_text.encode('utf-8')))
        root = doc.getroot()

        # Namespaces
        ns = {
            'soap': 'http://schemas.xmlsoap.org/soap/envelope/',
            'tns': 'http://www.apis-it.hr/fin/2012/types/f73'
        }

        # Try to find JIR
        jir_elem = root.find('.//tns:Jir', ns)
        if jir_elem is not None:
            return {
                "success": True,
                "jir": jir_elem.text,
                "errors": []
            }

        # Try to find errors
        errors = []
        error_elems = root.findall('.//tns:Greska', ns)
        for err in error_elems:
            code = err.findtext('tns:SifraGreske', default='', namespaces=ns)
            msg = err.findtext('tns:PorukaGreske', default='', namespaces=ns)
            errors.append({"code": code, "message": msg})

        return {
            "success": False,
            "jir": None,
            "errors": errors
        }

    except Exception as e:
        return {
            "success": False,
            "jir": None,
            "errors": [{"code": "PARSE_ERROR", "message": str(e)}]
        }


async def main():
    from config.company_config import get_company_config
    from tools.api_implementations.xades_signer import (
        load_certificate_from_file,
        calculate_zki
    )
    from tools.api_implementations.fina_xml_builder import build_racun_zahtjev

    config = get_company_config()
    now = datetime.now(timezone.utc)

    print("="*70)
    print("FINA FISKALIZACIJA TEST v2")
    print("="*70)
    print(f"Vrijeme: {now.strftime('%d.%m.%Y %H:%M:%S')}")
    print(f"Tvrtka: {config.name}")
    print(f"OIB: {config.oib}")
    print()

    # Load certificate
    print("[1/5] Učitavanje certifikata...")
    cert_info = load_certificate_from_file(str(CERT_PATH), CERT_PASSWORD)
    print(f"      OK - {cert_info.subject}")

    # Generate invoice number
    print("\n[2/5] Generiranje broja računa...")
    broj_racuna = now.strftime("%y%m%d%H%M%S")
    oznaka_pp = "1"
    oznaka_nu = "1"
    invoice_number = f"{broj_racuna}/{oznaka_pp}/{oznaka_nu}"
    print(f"      Broj: {invoice_number}")

    # Invoice data
    ukupan_iznos = Decimal("125.00")
    neto = Decimal("100.00")
    pdv_iznos = Decimal("25.00")

    print(f"      Neto: {neto} EUR")
    print(f"      PDV:  {pdv_iznos} EUR")
    print(f"      Ukupno: {ukupan_iznos} EUR")

    # Calculate ZKI
    print("\n[3/5] Izračun ZKI...")
    zki = calculate_zki(
        oib=config.oib,
        invoice_datetime=now,
        invoice_number=broj_racuna,
        business_unit=oznaka_pp,
        device_number=oznaka_nu,
        total_amount=ukupan_iznos,
        private_key=cert_info.private_key
    )
    print(f"      ZKI: {zki}")

    # Build RacunZahtjev XML
    print("\n[4/5] Generiranje FINA XML...")
    racun_xml = build_racun_zahtjev(
        oib=config.oib,
        u_sustavu_pdv=True,
        datum_vrijeme=now,
        oznaka_slijednosti="P",
        broj_racuna=broj_racuna,
        oznaka_poslovnog_prostora=oznaka_pp,
        oznaka_naplatnog_uredaja=oznaka_nu,
        ukupan_iznos=str(ukupan_iznos),
        nacin_placanja="G",  # Gotovina
        oib_operatera=config.oib,
        zki=zki,
        pdv=[{
            "stopa": "25.00",
            "osnovica": str(neto),
            "iznos": str(pdv_iznos)
        }]
    )
    print(f"      XML veličina: {len(racun_xml)} bytes")

    # Sign XML
    print("\n[5/5] Digitalno potpisivanje...")
    signed_xml = sign_racun_zahtjev(racun_xml)
    print(f"      Potpisani XML: {len(signed_xml)} bytes")

    # Preview
    print("\n" + "="*70)
    print("PREGLED")
    print("="*70)
    print(f"Račun: {invoice_number}")
    print(f"ZKI: {zki}")
    print(f"Iznos: {ukupan_iznos} EUR")
    print()

    # Confirm
    confirm = input("Poslati na FINA sandbox? (da/ne): ").strip().lower()
    if confirm != "da":
        print("Otkazano.")
        return 0

    # Send
    print("\n" + "="*70)
    print("SLANJE NA FINA")
    print("="*70)

    result = send_to_fina_sandbox(signed_xml)
    print(f"HTTP Status: {result['status_code']}")

    parsed = parse_fina_response(result['response_text'])

    print()
    if parsed["success"]:
        print("*" * 50)
        print("*  FISKALIZACIJA USPJEŠNA!                       *")
        print("*" * 50)
        print(f"\nJIR: {parsed['jir']}")
        print(f"ZKI: {zki}")
        print(f"Račun: {invoice_number}")
        print(f"Iznos: {ukupan_iznos} EUR")
    else:
        print("GREŠKE:")
        for err in parsed["errors"]:
            print(f"  [{err['code']}] {err['message']}")
        print("\nOdgovor servera:")
        print(result['response_text'][:2000])

    return 0 if parsed["success"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
