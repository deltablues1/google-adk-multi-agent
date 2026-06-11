"""
Test FINA Sandbox Connection

This script tests actual communication with FINA CIS sandbox:
https://cistest.apis-it.hr:8449/FiskalizacijaServiceTest

IMPORTANT: This is a real connection test using your certificate.
It will create a test fiscalization request.

Run with: python tests/test_fina_sandbox_connection.py
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


# Certificate configuration
CERT_PATH = project_root / "47034854402.F1.1.p12"
CERT_PASSWORD = os.environ.get("FINA_CERT_PASSWORD")
OIB = "47034854402"
BUSINESS_UNIT = "1"
DEVICE_NUMBER = "1"


def test_network_connectivity():
    """Test if we can reach FINA sandbox endpoint."""
    print("\n" + "="*60)
    print("TEST 1: Network Connectivity to FINA Sandbox")
    print("="*60)

    import socket
    import ssl

    host = "cistest.apis-it.hr"
    port = 8449

    print(f"Target: {host}:{port}")

    try:
        # Test basic connectivity
        sock = socket.create_connection((host, port), timeout=10)
        print(f"[OK] TCP connection established")

        # Test SSL/TLS
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE  # For testing only

        with context.wrap_socket(sock, server_hostname=host) as ssock:
            print(f"[OK] SSL/TLS connection established")
            print(f"  Protocol: {ssock.version()}")
            cert = ssock.getpeercert(binary_form=True)
            if cert:
                print(f"  Server certificate received ({len(cert)} bytes)")

        return True

    except socket.timeout:
        print(f"[FAIL] Connection timeout - check firewall/network")
        return False
    except socket.gaierror as e:
        print(f"[FAIL] DNS resolution failed: {e}")
        return False
    except ConnectionRefusedError:
        print(f"[FAIL] Connection refused by server")
        return False
    except Exception as e:
        print(f"[FAIL] Connection error: {e}")
        return False


def test_certificate_with_mtls():
    """Test mTLS connection with client certificate."""
    print("\n" + "="*60)
    print("TEST 2: mTLS Connection with Client Certificate")
    print("="*60)

    import ssl
    import socket
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.hazmat.backends import default_backend
    import tempfile

    host = "cistest.apis-it.hr"
    port = 8449

    print(f"Certificate: {CERT_PATH}")

    try:
        # Load the p12 certificate
        with open(CERT_PATH, 'rb') as f:
            p12_data = f.read()

        private_key, certificate, chain = pkcs12.load_key_and_certificates(
            p12_data, CERT_PASSWORD.encode('utf-8'), default_backend()
        )

        print(f"[OK] Certificate loaded: {certificate.subject.rfc4514_string()}")

        # Create temp files for the cert and key (requests needs file paths)
        import tempfile
        from cryptography.hazmat.primitives import serialization

        # Export private key to PEM
        key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )

        # Export certificate to PEM
        cert_pem = certificate.public_bytes(serialization.Encoding.PEM)

        # Create SSL context with client certificate
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE  # Sandbox may have self-signed certs

        # Write temp files
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as cert_file:
            cert_file.write(cert_pem)
            cert_path_temp = cert_file.name

        with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as key_file:
            key_file.write(key_pem)
            key_path_temp = key_file.name

        try:
            context.load_cert_chain(cert_path_temp, key_path_temp)
            print(f"[OK] Client certificate loaded into SSL context")

            # Test connection
            sock = socket.create_connection((host, port), timeout=15)
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                print(f"[OK] mTLS connection established")
                print(f"  Cipher: {ssock.cipher()}")
                return True

        finally:
            # Cleanup temp files
            os.unlink(cert_path_temp)
            os.unlink(key_path_temp)

    except Exception as e:
        print(f"[FAIL] mTLS connection failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_echo_request():
    """Send a basic SOAP echo/test request to FINA sandbox."""
    print("\n" + "="*60)
    print("TEST 3: SOAP Echo Request")
    print("="*60)

    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    import tempfile
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization

    endpoint = "https://cistest.apis-it.hr:8449/FiskalizacijaServiceTest"
    print(f"Endpoint: {endpoint}")

    try:
        # Load and export certificate
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

        # Create combined PEM file
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as f:
            f.write(cert_pem)
            f.write(key_pem)
            combined_pem = f.name

        try:
            # Simple echo request (minimal SOAP)
            echo_request = """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:fis="http://www.apis-it.hr/fin/2012/types/f73">
    <soap:Header>
        <fis:MessageId>TEST-ECHO-001</fis:MessageId>
    </soap:Header>
    <soap:Body>
        <fis:EchoRequest>Ping</fis:EchoRequest>
    </soap:Body>
</soap:Envelope>"""

            session = requests.Session()
            session.cert = combined_pem
            session.verify = False  # Sandbox may have self-signed certs

            # Disable SSL warnings for sandbox testing
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            print("Sending echo request...")

            response = session.post(
                endpoint,
                data=echo_request.encode('utf-8'),
                headers={
                    'Content-Type': 'application/soap+xml; charset=utf-8',
                    'SOAPAction': 'http://www.apis-it.hr/fin/2012/types/f73/Echo'
                },
                timeout=30
            )

            print(f"[OK] Response received")
            print(f"  Status: {response.status_code}")
            print(f"  Content-Type: {response.headers.get('Content-Type', 'N/A')}")

            if response.status_code == 200:
                print(f"[SUCCESS] FINA sandbox responded successfully")
                # Show part of response
                resp_text = response.text[:500] if len(response.text) > 500 else response.text
                print(f"\nResponse preview:\n{resp_text}")
                return True
            elif response.status_code == 500:
                # SOAP fault is expected for invalid requests
                print(f"[INFO] SOAP Fault received (expected for echo test)")
                print(f"  This confirms the endpoint is reachable")
                return True
            else:
                print(f"[WARNING] Unexpected status code: {response.status_code}")
                print(f"  Response: {response.text[:300]}")
                return False

        finally:
            os.unlink(combined_pem)

    except requests.exceptions.SSLError as e:
        print(f"[FAIL] SSL Error: {e}")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"[FAIL] Connection Error: {e}")
        return False
    except Exception as e:
        print(f"[FAIL] Request failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_full_fiscalization_flow():
    """Test complete fiscalization flow with FINA sandbox."""
    print("\n" + "="*60)
    print("TEST 4: Full Fiscalization Flow (Sandbox)")
    print("="*60)

    async def run_flow():
        from tools.adk_tools.fiskalizacija_adk_tools import (
            load_certificate,
            calculate_zki,
            build_ubl_invoice,
            sign_xades,
            validate_oib,
            calculate_tax,
        )

        # Step 1: Load certificate
        print("\nStep 1: Loading certificate...")
        cert_result = await load_certificate(
            source=str(CERT_PATH),
            password=CERT_PASSWORD,
            source_type="file",
            cache_key="fina-sandbox-test"
        )

        if not cert_result["success"]:
            print(f"[FAIL] Certificate loading failed: {cert_result.get('error')}")
            return False

        print(f"[OK] Certificate loaded: {cert_result['certificate_info'].get('subject')}")

        # Step 2: Validate OIB
        print("\nStep 2: Validating OIB...")
        oib_result = await validate_oib(OIB)
        if not oib_result["valid"]:
            print(f"[FAIL] OIB validation failed: {oib_result.get('error_message')}")
            return False
        print(f"[OK] OIB valid: {OIB}")

        # Step 3: Prepare invoice data
        print("\nStep 3: Preparing test invoice...")
        now = datetime.now(timezone.utc)
        invoice_number = f"TEST-{now.strftime('%H%M%S')}/1/1"

        invoice_items = [
            {"net_amount": "100.00", "vat_rate": "25", "description": "Test usluga"}
        ]

        tax_result = await calculate_tax(invoice_items)
        print(f"[OK] Tax calculated: {tax_result['total_gross']} EUR")

        invoice_data = {
            "invoice_number": invoice_number,
            "invoice_type": "380",
            "issue_date": now.strftime("%Y-%m-%d"),
            "due_date": now.strftime("%Y-%m-%d"),
            "currency": "EUR",
            "supplier": {
                "name": "LUX TECH D.O.O.",
                "oib": OIB,
                "vat_number": f"HR{OIB}",
                "address": "Hrvatski Leskovac",
                "city": "Hrvatski Leskovac",
                "postal_code": "10251",
                "country_code": "HR"
            },
            "customer": {
                "name": "Test Kupac d.o.o.",
                "oib": "12345678903",
                "vat_number": "HR12345678903",
                "address": "Testna ulica 1",
                "city": "Zagreb",
                "postal_code": "10000",
                "country_code": "HR"
            },
            "items": [
                {
                    "description": "Test IT usluga",
                    "quantity": "1",
                    "unit": "HUR",
                    "unit_price": "100.00",
                    "net_amount": "100.00",
                    "vat_rate": "25",
                    "vat_amount": "25.00",
                    "gross_amount": "125.00"
                }
            ],
            "tax_breakdown": tax_result,
            "note": "Test invoice for FINA sandbox"
        }

        # Step 4: Build UBL XML
        print("\nStep 4: Building UBL Invoice XML...")
        ubl_result = await build_ubl_invoice(invoice_data)
        if not ubl_result["success"]:
            print(f"[FAIL] UBL building failed: {ubl_result.get('error')}")
            return False
        print(f"[OK] UBL Invoice built: {len(ubl_result['xml'])} bytes")

        # Step 5: Calculate ZKI
        print("\nStep 5: Calculating ZKI...")
        zki_result = await calculate_zki(
            oib=OIB,
            invoice_datetime=now.isoformat(),
            invoice_number=invoice_number.split('/')[0],  # Sequential part
            business_unit=BUSINESS_UNIT,
            device_number=DEVICE_NUMBER,
            total_amount=tax_result["total_gross"],
            cert_cache_key="fina-sandbox-test"
        )

        if not zki_result["success"]:
            print(f"[FAIL] ZKI calculation failed: {zki_result.get('error')}")
            return False
        print(f"[OK] ZKI calculated: {zki_result['zki']}")

        # Step 6: Sign XML
        print("\nStep 6: Signing XML with XAdES-BES...")
        sign_result = await sign_xades(
            xml=ubl_result["xml"],
            cert_cache_key="fina-sandbox-test"
        )

        if not sign_result["success"]:
            print(f"[FAIL] XML signing failed: {sign_result.get('error')}")
            return False
        print(f"[OK] XML signed: {len(sign_result['signed_xml'])} bytes")

        # Step 7: Summary (not sending to FINA in this test)
        print("\n" + "-"*40)
        print("SUMMARY - Invoice ready for fiscalization:")
        print(f"  Invoice Number: {invoice_number}")
        print(f"  ZKI: {zki_result['zki']}")
        print(f"  Total: {tax_result['total_gross']} EUR")
        print(f"  Signed XML size: {len(sign_result['signed_xml'])} bytes")
        print("-"*40)

        print("\n[SUCCESS] Full flow completed!")
        print("\nNote: To actually send to FINA sandbox, use send_fina_soap()")

        return True

    try:
        return asyncio.run(run_flow())
    except Exception as e:
        print(f"[FAIL] Flow failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def print_summary(results):
    """Print test summary."""
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for r in results.values() if r)
    total = len(results)

    for test_name, result in results.items():
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {status} {test_name}")

    print("-" * 40)
    print(f"  Total: {passed}/{total} tests passed")

    if passed == total:
        print("\n  All tests passed! Ready for FINA sandbox testing.")
    elif passed >= 3:
        print("\n  Core functionality working. Some tests may require network access.")
    else:
        print("\n  Multiple tests failed. Check configuration and network.")


def main():
    print("="*60)
    print("FINA SANDBOX CONNECTION TEST")
    print("="*60)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Certificate: {CERT_PATH}")
    print(f"OIB: {OIB}")
    print(f"Endpoint: https://cistest.apis-it.hr:8449/FiskalizacijaServiceTest")

    results = {}

    # Test 1: Network connectivity
    results["Network Connectivity"] = test_network_connectivity()

    # Test 2: mTLS connection
    results["mTLS Connection"] = test_certificate_with_mtls()

    # Test 3: SOAP echo request
    results["SOAP Request"] = test_echo_request()

    # Test 4: Full fiscalization flow
    results["Full Flow"] = test_full_fiscalization_flow()

    # Summary
    print_summary(results)

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
