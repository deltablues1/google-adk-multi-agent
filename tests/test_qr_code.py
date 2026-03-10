"""
Test QR Code Generation for Croatian Fiscalization

Tests the QR code generation according to Porezna uprava specification.

Official URL format:
    https://porezna.gov.hr/rn?jir=XXXXX&datv=YYYYMMDD_HHMM&izn=CCCCC

Requirements:
- Minimum size: 2cm x 2cm on printed receipt
- Date format: YYYYMMDD_HHMM
- Amount: in cents (integer)

Run with: python tests/test_qr_code.py
"""

import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_qr_code_generation():
    """Test QR code generation with sample data."""
    from tools.api_implementations.fina_soap_client import generate_verification_qr

    print("=" * 60)
    print("TEST QR CODE GENERATION")
    print("=" * 60)

    # Sample data from successful fiscalization
    jir = "af0b1b03-7881-4a82-8a73-4586a0257cba"
    zki = "482BDD47-85E3F833-31FB6802-9BF0826E"
    invoice_datetime = "23.01.2026T19:20:21"
    total_amount = "125.00"
    oib = "47034854402"

    print(f"\nTest data:")
    print(f"  JIR: {jir}")
    print(f"  ZKI: {zki}")
    print(f"  Datum: {invoice_datetime}")
    print(f"  Iznos: {total_amount} EUR")

    # Test 1: Generate with JIR
    print("\n[Test 1] QR kod sa JIR...")
    result_jir = generate_verification_qr(
        jir=jir,
        zki=zki,
        invoice_datetime=invoice_datetime,
        total_amount=total_amount,
        oib=oib,
        use_jir=True,
        min_size_cm=2.0,
        dpi=300
    )

    if result_jir["success"]:
        print(f"  OK - URL: {result_jir['verification_url']}")
        print(f"  Minimalna velicina: {result_jir['min_size_cm']} cm")
        print(f"  Pixeli pri 300 DPI: {result_jir['pixel_size']}")
        print(f"  PNG base64 duljina: {len(result_jir['qr_code_base64'])} znakova")
        if result_jir.get('qr_code_svg'):
            print(f"  SVG dostupan: Da")
    else:
        print(f"  GRESKA: {result_jir['error']}")
        return False

    # Validate URL format
    url = result_jir['verification_url']
    expected_base = "https://porezna.gov.hr/rn"
    if not url.startswith(expected_base):
        print(f"  GRESKA: URL ne pocinje sa {expected_base}")
        return False

    if "jir=" not in url:
        print("  GRESKA: URL ne sadrzi jir parametar")
        return False

    if "datv=" not in url:
        print("  GRESKA: URL ne sadrzi datv parametar")
        return False

    if "izn=" not in url:
        print("  GRESKA: URL ne sadrzi izn parametar")
        return False

    # Check date format (YYYYMMDD_HHMM)
    import re
    date_match = re.search(r'datv=(\d{8}_\d{4})', url)
    if not date_match:
        print("  GRESKA: Datum nije u ispravnom formatu YYYYMMDD_HHMM")
        return False
    print(f"  Datum u URL-u: {date_match.group(1)}")

    # Check amount (should be in cents)
    amount_match = re.search(r'izn=(\d+)', url)
    if not amount_match:
        print("  GRESKA: Iznos nije u ispravnom formatu")
        return False
    amount_cents = int(amount_match.group(1))
    expected_cents = 12500  # 125.00 EUR = 12500 cents
    if amount_cents != expected_cents:
        print(f"  GRESKA: Iznos je {amount_cents}, ocekivano {expected_cents}")
        return False
    print(f"  Iznos u URL-u: {amount_cents} centi")

    # Test 2: Generate with ZKI
    print("\n[Test 2] QR kod sa ZKI...")
    result_zki = generate_verification_qr(
        jir=jir,
        zki=zki,
        invoice_datetime=invoice_datetime,
        total_amount=total_amount,
        oib=oib,
        use_jir=False,
        min_size_cm=2.0,
        dpi=300
    )

    if result_zki["success"]:
        print(f"  OK - URL: {result_zki['verification_url']}")
        if "zki=" in result_zki['verification_url']:
            print("  ZKI parametar prisutan")
        else:
            print("  GRESKA: ZKI parametar nije prisutan")
            return False
    else:
        print(f"  GRESKA: {result_zki['error']}")
        return False

    # Test 3: Save sample QR codes
    print("\n[Test 3] Spremanje uzoraka...")
    try:
        import base64

        # Save PNG
        png_path = project_root / "tests" / "sample_qr_jir.png"
        with open(png_path, "wb") as f:
            f.write(base64.b64decode(result_jir["qr_code_base64"]))
        print(f"  PNG spremljen: {png_path}")

        # Save SVG if available
        if result_jir.get("qr_code_svg"):
            svg_path = project_root / "tests" / "sample_qr_jir.svg"
            with open(svg_path, "w", encoding="utf-8") as f:
                f.write(result_jir["qr_code_svg"])
            print(f"  SVG spremljen: {svg_path}")

    except Exception as e:
        print(f"  Upozorenje: Nije moguce spremiti datoteke: {e}")

    # Summary
    print("\n" + "=" * 60)
    print("SAZETA")
    print("=" * 60)
    print(f"QR kod URL format: https://porezna.gov.hr/rn?jir/zki=...&datv=...&izn=...")
    print(f"Datum format: YYYYMMDD_HHMM (bez sekundi)")
    print(f"Iznos format: u centima (cijeli broj)")
    print(f"Minimalna velicina: 2cm x 2cm")
    print(f"DPI za tisak: 300")
    print(f"Pixeli za 2cm: ~{int((2.0 / 2.54) * 300)}")
    print()
    print("SVI TESTOVI USPJESNI!")
    print("=" * 60)

    return True


def test_edge_cases():
    """Test edge cases and error handling."""
    from tools.api_implementations.fina_soap_client import generate_verification_qr

    print("\n" + "=" * 60)
    print("TEST EDGE CASES")
    print("=" * 60)

    # Test without JIR when use_jir=True
    print("\n[Edge 1] Bez JIR-a kad je use_jir=True...")
    result = generate_verification_qr(
        jir=None,
        zki="482BDD4785E3F83331FB68029BF0826E",
        invoice_datetime="2026-01-23T19:20:21",
        total_amount="125.00",
        use_jir=True
    )
    if not result["success"] and "JIR is required" in result["error"]:
        print("  OK - Ispravno detektirana greska")
    else:
        print("  GRESKA - Trebala je biti greska")

    # Test without ZKI when use_jir=False
    print("\n[Edge 2] Bez ZKI-a kad je use_jir=False...")
    result = generate_verification_qr(
        jir="af0b1b03-7881-4a82-8a73-4586a0257cba",
        zki=None,
        invoice_datetime="2026-01-23T19:20:21",
        total_amount="125.00",
        use_jir=False
    )
    if not result["success"] and "ZKI is required" in result["error"]:
        print("  OK - Ispravno detektirana greska")
    else:
        print("  GRESKA - Trebala je biti greska")

    # Test with various datetime formats
    print("\n[Edge 3] Razni formati datuma...")
    datetime_formats = [
        "2026-01-23T19:20:21",
        "2026-01-23T19:20:21Z",
        "2026-01-23T19:20:21+01:00",
        "23.01.2026T19:20:21",
        "23.01.2026 19:20:21",
    ]

    for dt_str in datetime_formats:
        result = generate_verification_qr(
            jir="af0b1b03-7881-4a82-8a73-4586a0257cba",
            invoice_datetime=dt_str,
            total_amount="100.00",
            use_jir=True
        )
        status = "OK" if result["success"] else "FAIL"
        print(f"  {status}: {dt_str}")

    print("\nEdge case testovi zavrseni.")
    return True


if __name__ == "__main__":
    success = test_qr_code_generation()
    if success:
        test_edge_cases()
    sys.exit(0 if success else 1)
