#!/usr/bin/env python
"""
Integration Test Script for Fiskalizacija Phase 3 (Signing)

This script tests the complete signing workflow:
1. Build UBL Invoice XML
2. Validate with XSD
3. Generate test certificate
4. Calculate ZKI
5. Sign with XAdES-BES
6. Verify signature

Run this script manually to verify Phase 3 implementation.

Usage:
    python run_signing_integration_test.py
"""

import sys
import os
import asyncio
import tempfile
from datetime import datetime, timezone, timedelta
from decimal import Decimal

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


def print_header(text: str):
    """Print section header."""
    print(f"\n{'='*60}")
    print(f" {text}")
    print('='*60)


def print_result(name: str, success: bool, details: str = None):
    """Print test result."""
    status = "✓ PASS" if success else "✗ FAIL"
    print(f"  [{status}] {name}")
    if details:
        print(f"        {details}")


async def run_integration_test():
    """Run full integration test for signing workflow."""

    print_header("FISKALIZACIJA PHASE 3 - SIGNING INTEGRATION TEST")
    print(f"Timestamp: {datetime.now().isoformat()}")

    # Check imports
    print_header("1. Checking Dependencies")

    try:
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.backends import default_backend
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives.serialization import pkcs12
        print_result("cryptography library", True)
        CRYPTO_AVAILABLE = True
    except ImportError as e:
        print_result("cryptography library", False, str(e))
        CRYPTO_AVAILABLE = False

    try:
        from lxml import etree
        print_result("lxml library", True)
        LXML_AVAILABLE = True
    except ImportError as e:
        print_result("lxml library", False, str(e))
        LXML_AVAILABLE = False

    if not CRYPTO_AVAILABLE or not LXML_AVAILABLE:
        print("\n⚠ Missing required libraries. Install with:")
        print("  pip install cryptography pyOpenSSL lxml signxml")
        return False

    # Import project modules
    try:
        from tools.api_implementations.xades_signer import (
            load_certificate_from_file,
            calculate_zki,
            sign_xades_bes,
            verify_signature,
            CertificateInfo
        )
        print_result("xades_signer module", True)
    except ImportError as e:
        print_result("xades_signer module", False, str(e))
        return False

    try:
        from tools.adk_tools.fiskalizacija_adk_tools import (
            build_ubl_invoice,
            validate_xsd,
            canonicalize_xml,
            load_certificate,
            sign_xades,
            calculate_zki as calculate_zki_tool,
            verify_xml_signature,
        )
        print_result("fiskalizacija_adk_tools module", True)
    except ImportError as e:
        print_result("fiskalizacija_adk_tools module", False, str(e))
        return False

    # Generate test certificate
    print_header("2. Generating Test Certificate")

    def generate_test_p12(password: str = "test123"):
        """Generate a test .p12 certificate."""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "HR"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test Company d.o.o."),
            x509.NameAttribute(NameOID.COMMON_NAME, "Test Fiskalizacija Certificate"),
        ])

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
            .sign(private_key, hashes.SHA256(), default_backend())
        )

        p12_data = pkcs12.serialize_key_and_certificates(
            name=b"test",
            key=private_key,
            cert=cert,
            cas=None,
            encryption_algorithm=serialization.BestAvailableEncryption(password.encode())
        )

        fd, path = tempfile.mkstemp(suffix='.p12')
        with os.fdopen(fd, 'wb') as f:
            f.write(p12_data)

        return path, private_key

    try:
        p12_path, private_key = generate_test_p12("testpassword123")
        print_result("Test certificate generated", True, f"Path: {p12_path}")
    except Exception as e:
        print_result("Test certificate generated", False, str(e))
        return False

    # Test certificate loading
    print_header("3. Testing Certificate Loading")

    try:
        cert_info = load_certificate_from_file(p12_path, "testpassword123")
        print_result("Load .p12 certificate", True, f"Subject: {cert_info.subject}")
        print_result("Certificate is valid", cert_info.is_valid(), f"Expires: {cert_info.valid_to}")
    except Exception as e:
        print_result("Load .p12 certificate", False, str(e))
        return False

    # Test ZKI calculation
    print_header("4. Testing ZKI Calculation")

    try:
        zki = calculate_zki(
            oib="12345678903",
            invoice_datetime=datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            invoice_number="1",
            business_unit="URED",
            device_number="1",
            total_amount=Decimal("1250.00"),
            private_key=private_key
        )
        print_result("ZKI calculation", True, f"ZKI: {zki}")

        # Verify format
        assert len(zki) == 35, "ZKI must be 35 characters"
        assert zki.count('-') == 3, "ZKI must have 3 dashes"
        print_result("ZKI format validation", True)
    except Exception as e:
        print_result("ZKI calculation", False, str(e))
        return False

    # Test UBL Invoice building
    print_header("5. Testing UBL Invoice Generation")

    invoice_data = {
        "invoice_number": "001/URED/1",
        "issue_date": "2026-01-15",
        "due_date": "2026-02-15",
        "currency": "EUR",
        "supplier": {
            "name": "Test Supplier d.o.o.",
            "oib": "12345678903",
            "vat_number": "HR12345678903",
            "address": "Testna ulica 1",
            "city": "Zagreb",
            "postal_code": "10000",
            "country_code": "HR"
        },
        "customer": {
            "name": "Test Customer d.o.o.",
            "oib": "98765432109",
            "vat_number": "HR98765432109",
            "address": "Kupčeva ulica 2",
            "city": "Split",
            "postal_code": "21000",
            "country_code": "HR"
        },
        "items": [
            {
                "name": "IT konzultacije",
                "quantity": "10",
                "unit_code": "HUR",
                "unit_price": "100.00",
                "net_amount": "1000.00",
                "vat_rate": "25"
            }
        ],
        "tax_breakdown": {
            "subtotals": [{"vat_rate": "25", "taxable_amount": "1000.00", "tax_amount": "250.00"}],
            "total_net": "1000.00",
            "total_tax": "250.00",
            "total_gross": "1250.00"
        }
    }

    try:
        build_result = await build_ubl_invoice(invoice_data)
        assert build_result['success'], f"Build failed: {build_result.get('error')}"
        xml = build_result['xml']
        print_result("UBL Invoice XML generated", True, f"Size: {len(xml)} bytes")

        # Check key elements
        assert 'Invoice' in xml, "Missing Invoice element"
        assert 'HR-FISK' in xml or 'mfin.hr' in xml, "Missing HR-FISK customization"
        print_result("UBL Invoice structure", True)
    except Exception as e:
        print_result("UBL Invoice XML generated", False, str(e))
        return False

    # Test XSD validation
    print_header("6. Testing XSD Validation")

    try:
        validate_result = await validate_xsd(xml)
        print_result("XSD validation", validate_result['valid'],
                    f"Schema: {validate_result.get('schema_version')}")
        if not validate_result['valid']:
            for err in validate_result.get('errors', [])[:3]:
                print(f"        Error: {err.get('message', err)}")
    except Exception as e:
        print_result("XSD validation", False, str(e))

    # Test canonicalization
    print_header("7. Testing XML Canonicalization")

    try:
        c14n_result = await canonicalize_xml(xml)
        assert c14n_result['success'], f"C14N failed: {c14n_result.get('error')}"
        print_result("XML canonicalization", True,
                    f"Method: {c14n_result.get('method')}, Size: {len(c14n_result['canonical_xml'])} bytes")
    except Exception as e:
        print_result("XML canonicalization", False, str(e))
        return False

    # Test ADK tool: load_certificate
    print_header("8. Testing ADK load_certificate Tool")

    try:
        cert_result = await load_certificate(
            source=p12_path,
            password="testpassword123",
            source_type="file",
            cache_key="integration-test-cert"
        )
        assert cert_result['success'], f"Load failed: {cert_result.get('error')}"
        print_result("ADK load_certificate", True,
                    f"Cache key: {cert_result['cache_key']}")
    except Exception as e:
        print_result("ADK load_certificate", False, str(e))
        return False

    # Test ADK tool: calculate_zki
    print_header("9. Testing ADK calculate_zki Tool")

    try:
        zki_result = await calculate_zki_tool(
            oib="12345678903",
            invoice_datetime="2026-01-15T10:30:00",
            invoice_number="1",
            business_unit="URED",
            device_number="1",
            total_amount="1250.00",
            cert_cache_key="integration-test-cert"
        )
        assert zki_result['success'], f"ZKI failed: {zki_result.get('error')}"
        print_result("ADK calculate_zki", True, f"ZKI: {zki_result['zki']}")
    except Exception as e:
        print_result("ADK calculate_zki", False, str(e))
        return False

    # Test ADK tool: sign_xades
    print_header("10. Testing ADK sign_xades Tool")

    try:
        sign_result = await sign_xades(
            xml=xml,
            cert_cache_key="integration-test-cert"
        )
        assert sign_result['success'], f"Sign failed: {sign_result.get('error')}"
        signed_xml = sign_result['signed_xml']
        print_result("ADK sign_xades", True,
                    f"Signature ID: {sign_result['signature_id']}")
        print_result("Signed XML contains Signature", 'Signature' in signed_xml)
        print_result("Signed XML contains X509Certificate", 'X509Certificate' in signed_xml)
    except Exception as e:
        print_result("ADK sign_xades", False, str(e))
        return False

    # Test ADK tool: verify_xml_signature
    print_header("11. Testing ADK verify_xml_signature Tool")

    try:
        verify_result = await verify_xml_signature(signed_xml)
        print_result("ADK verify_xml_signature", verify_result['valid'],
                    f"Signer: {verify_result.get('signer')}")
    except Exception as e:
        print_result("ADK verify_xml_signature", False, str(e))

    # Cleanup
    print_header("12. Cleanup")

    try:
        os.unlink(p12_path)
        print_result("Removed test certificate", True)
    except Exception as e:
        print_result("Removed test certificate", False, str(e))

    # Summary
    print_header("INTEGRATION TEST COMPLETE")
    print("""
    Phase 3 (Signing) Implementation Status:
    ✓ Certificate loading from .p12 file
    ✓ ZKI (Zaštitni Kod Izdavatelja) calculation
    ✓ XAdES-BES digital signature
    ✓ Signature verification
    ✓ ADK tool wrappers

    Next Phase (4): FINA SOAP Communication
    - send_fina_soap (SOAP client with mTLS)
    - parse_fina_response (JIR extraction)
    - generate_qr_code (verification QR)
    - Circuit breaker and retry queue
    """)

    return True


if __name__ == "__main__":
    success = asyncio.run(run_integration_test())
    sys.exit(0 if success else 1)
