"""
Test FINA Certificate Integration

This script tests:
1. Loading the .p12 certificate
2. Reading certificate details (subject, issuer, validity)
3. ZKI calculation with the certificate
4. Basic signing capability

Run with: python tests/test_certificate_integration.py
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_certificate_loading():
    """Test loading the FINA .p12 certificate."""
    print("\n" + "="*60)
    print("TEST 1: Certificate Loading")
    print("="*60)

    from tools.api_implementations.xades_signer import load_certificate_from_file

    cert_path = project_root / "47034854402.F1.1.p12"
    cert_password = "NinuPiL1903"

    if not cert_path.exists():
        print(f"[FAIL] Certificate file not found: {cert_path}")
        return None

    print(f"Certificate file: {cert_path}")
    print(f"File size: {cert_path.stat().st_size} bytes")

    try:
        cert_info = load_certificate_from_file(str(cert_path), cert_password)

        print("\n[SUCCESS] Certificate loaded successfully!")
        print("-" * 40)
        print(f"Subject: {cert_info.subject}")
        print(f"Issuer: {cert_info.issuer}")
        print(f"Serial Number: {cert_info.serial_number}")
        print(f"Valid From: {cert_info.valid_from}")
        print(f"Valid To: {cert_info.valid_to}")
        print(f"Is Valid Now: {cert_info.is_valid()}")
        print(f"Chain Length: {len(cert_info.certificate_chain)}")

        # Check if certificate is for fiscalization (test or production)
        subject_lower = cert_info.subject.lower()
        if 'fina' in subject_lower or 'rdc' in subject_lower:
            print("\n[INFO] This appears to be a FINA-issued certificate")

        # Check validity
        if cert_info.is_valid():
            print("\n[OK] Certificate is currently valid")
        else:
            now = datetime.now()
            if cert_info.valid_from and now < cert_info.valid_from:
                print("\n[WARNING] Certificate is not yet valid!")
            if cert_info.valid_to and now > cert_info.valid_to:
                print("\n[WARNING] Certificate has expired!")

        return cert_info

    except Exception as e:
        print(f"\n[FAIL] Failed to load certificate: {e}")
        return None


def test_zki_calculation(cert_info):
    """Test ZKI calculation with the certificate."""
    print("\n" + "="*60)
    print("TEST 2: ZKI Calculation")
    print("="*60)

    if cert_info is None:
        print("[SKIP] No certificate loaded")
        return False

    from tools.api_implementations.xades_signer import calculate_zki
    from decimal import Decimal

    # Test data
    test_oib = "47034854402"  # OIB from certificate filename
    test_datetime = datetime(2026, 1, 23, 12, 30, 0)
    test_invoice_number = "1"
    test_business_unit = "URED"
    test_device_number = "1"
    test_amount = Decimal("1250.00")

    print(f"\nTest data:")
    print(f"  OIB: {test_oib}")
    print(f"  DateTime: {test_datetime.strftime('%d.%m.%Y %H:%M:%S')}")
    print(f"  Invoice Number: {test_invoice_number}")
    print(f"  Business Unit: {test_business_unit}")
    print(f"  Device Number: {test_device_number}")
    print(f"  Amount: {test_amount} EUR")

    try:
        zki = calculate_zki(
            oib=test_oib,
            invoice_datetime=test_datetime,
            invoice_number=test_invoice_number,
            business_unit=test_business_unit,
            device_number=test_device_number,
            total_amount=test_amount,
            private_key=cert_info.private_key
        )

        print(f"\n[SUCCESS] ZKI calculated: {zki}")

        # Validate ZKI format (XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX)
        parts = zki.split('-')
        if len(parts) == 4 and all(len(p) == 8 for p in parts):
            print("[OK] ZKI format is valid (32 hex chars with dashes)")
        else:
            print("[WARNING] ZKI format unexpected")

        return True

    except Exception as e:
        print(f"\n[FAIL] ZKI calculation failed: {e}")
        return False


def test_xml_signing(cert_info):
    """Test basic XML signing capability."""
    print("\n" + "="*60)
    print("TEST 3: XML Signing")
    print("="*60)

    if cert_info is None:
        print("[SKIP] No certificate loaded")
        return False

    from tools.api_implementations.xades_signer import XAdESSigner

    # Simple test XML
    test_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2">
    <ID>TEST-001/URED/1</ID>
    <IssueDate>2026-01-23</IssueDate>
    <Note>Test invoice for signing</Note>
</Invoice>"""

    print("\nTest XML:")
    print(test_xml[:200] + "...")

    try:
        signer = XAdESSigner(cert_info)
        signed_xml = signer.sign(test_xml)

        print(f"\n[SUCCESS] XML signed successfully!")
        print(f"  Original size: {len(test_xml)} bytes")
        print(f"  Signed size: {len(signed_xml)} bytes")

        # Check for signature elements
        if '<ds:Signature' in signed_xml or '<Signature' in signed_xml:
            print("[OK] Signature element present in output")
        else:
            print("[WARNING] Signature element not found")

        if '<ds:SignatureValue' in signed_xml or '<SignatureValue' in signed_xml:
            print("[OK] SignatureValue element present")

        if '<xades:SigningTime' in signed_xml or '<SigningTime' in signed_xml:
            print("[OK] XAdES SigningTime present")

        return True

    except Exception as e:
        print(f"\n[FAIL] XML signing failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_adk_tool_integration():
    """Test the ADK tool layer for certificate operations."""
    print("\n" + "="*60)
    print("TEST 4: ADK Tools Integration")
    print("="*60)

    import asyncio
    from tools.adk_tools.fiskalizacija_adk_tools import (
        load_certificate,
        calculate_zki,
    )

    cert_path = str(project_root / "47034854402.F1.1.p12")
    cert_password = "NinuPiL1903"

    async def run_tests():
        # Test load_certificate
        print("\nTesting load_certificate ADK tool...")
        result = await load_certificate(
            source=cert_path,
            password=cert_password,
            source_type="file",
            cache_key="fina-test-cert"
        )

        if result["success"]:
            print(f"[SUCCESS] Certificate loaded via ADK tool")
            print(f"  Subject: {result['certificate_info'].get('subject', 'N/A')}")
            print(f"  Expires: {result['expires_at']}")
            print(f"  Cache key: {result['cache_key']}")

            # Test ZKI calculation via ADK tool
            print("\nTesting calculate_zki ADK tool...")
            zki_result = await calculate_zki(
                oib="47034854402",
                invoice_datetime="2026-01-23T12:30:00",
                invoice_number="1",
                business_unit="URED",
                device_number="1",
                total_amount="1250.00",
                cert_cache_key="fina-test-cert"
            )

            if zki_result["success"]:
                print(f"[SUCCESS] ZKI via ADK: {zki_result['zki']}")
                return True
            else:
                print(f"[FAIL] ZKI calculation failed: {zki_result.get('error')}")
                return False
        else:
            print(f"[FAIL] Certificate loading failed: {result.get('error')}")
            return False

    try:
        return asyncio.run(run_tests())
    except Exception as e:
        print(f"[FAIL] ADK test failed: {e}")
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
        print("\n  All tests passed! Certificate is ready for use.")
    else:
        print("\n  Some tests failed. Please check the output above.")


def main():
    print("="*60)
    print("FINA CERTIFICATE INTEGRATION TEST")
    print("="*60)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Project root: {project_root}")

    results = {}

    # Test 1: Certificate Loading
    cert_info = test_certificate_loading()
    results["Certificate Loading"] = cert_info is not None

    # Test 2: ZKI Calculation
    results["ZKI Calculation"] = test_zki_calculation(cert_info)

    # Test 3: XML Signing
    results["XML Signing"] = test_xml_signing(cert_info)

    # Test 4: ADK Tool Integration
    results["ADK Tools"] = test_adk_tool_integration()

    # Summary
    print_summary(results)

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
